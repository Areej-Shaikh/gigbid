"""Client Liaison (conversation graph, C1): read the newest client message, classify its intent,
draft a reply (or offer interview slots), check it, preview it, and wait for the human.

Safety:
  - the client message is untrusted: fenced in <client_message> tags, never followed
  - scam signals get a fixed, safe reply (no LLM involved, so an attacker cannot steer it)
  - Compliance removes contact details, off-platform asks, guarantees and prices below the floor
  - nothing is sent before interrupt() returns "approve"; sends use idempotency keys
"""
import re

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.config import cfg
from agent.handoffs import MessageApproval, MessageIntent, ReplyDraft
from agent.llm import structured
from agent.mcp_client import ToolCallError
from agent.memory.promotion_rules import apply_style, record_edit, style_rules
from agent.memory.store import current_store, user_of
from agent.nodes.common import budget_exceeded, prompt, sentences, thread_id, toolbox, trace
from agent.nodes.compliance import check

SAFE_SCAM_REPLY = ("Thanks for reaching out. To keep things safe for both of us, I keep all communication, "
                   "files and payments here on the platform, as its terms require. I'm happy to continue the "
                   "conversation in this chat whenever you're ready.")


def fence_message(text: str) -> str:
    text = text.replace("<client_message>", "").replace("</client_message>", "")
    return f"<client_message>\n{text}\n</client_message>"


def _key(state, config) -> str:
    return f"{thread_id(config)}-{state['incoming']['message_id']}"


# ---------------------------------------------------------------- read
async def read_messages(state, config: RunnableConfig):
    tb = toolbox(config)
    msgs = (await tb.call("liaison", "list_messages", client_id=state["client_id"]))["messages"]
    msgs.sort(key=lambda m: m["sent_at"])
    done = set(state.get("handled") or [])
    new = [m for m in msgs if m["sender"] == "client" and m["message_id"] not in done]
    if not new:
        return {"status": "no_new_messages", "trace": [trace("read_messages", new=0)]}
    incoming = new[-1]
    job_id = incoming.get("job_id") or state.get("job_id")
    job = {}
    if job_id:
        try:
            job = await tb.call("liaison", "get_job", job_id=job_id)
        except ToolCallError:
            job = {"job_id": job_id}
    # older unanswered client messages are folded into this reply (marked handled when it is sent)
    return {"incoming": incoming, "history": msgs[-10:], "job_id": job_id, "job": job, "status": "running",
            "draft": {}, "slots": [], "approval": {}, "preview": {}, "sent": {},
            "trace": [trace("read_messages", new=len(new), message_id=incoming["message_id"])]}


def route_after_read(state) -> str:
    return "end" if state.get("status") != "running" else "classify"


# ---------------------------------------------------------------- classify
def _rule_intent(text: str) -> MessageIntent:
    for r in cfg()["liaison"]["intents"]:
        if re.search(r["pattern"], text):
            return MessageIntent(intent=r["intent"], summary=text[:120], reasons=[f"rule: {r['intent']}"])
    return MessageIntent(intent="other", summary=text[:120], reasons=["no rule matched"])


async def classify(state, config=None):
    text = state["incoming"]["text"]
    rules = _rule_intent(text)
    llm, info = await structured("liaison_classify", MessageIntent, prompt("liaison_classify"),
                                 fence_message(text), lambda: rules)
    # safety net: an LLM can never "un-flag" a message the scam rules caught
    result = rules if rules.intent == "scam_signal" else llm
    return {"intent": result.model_dump(), "tokens": info["tokens"],
            "trace": [trace("classify", intent=result.intent, rule_intent=rules.intent, **info)]}


def route_after_classify(state) -> str:
    return "slots" if state["intent"]["intent"] == "interview_request" else "draft_reply"


# ---------------------------------------------------------------- slots
async def slots(state, config: RunnableConfig):
    c = cfg()["liaison"]
    try:
        res = await toolbox(config).call("liaison", "free_slots", days_ahead=c["slot_days_ahead"],
                                         duration_min=c["slot_minutes"], limit=c["slots_offered"])
        found = res["slots"]
    except ToolCallError as e:
        return {"slots": [], "errors": [f"free_slots: {e}"], "trace": [trace("slots", error=str(e))]}
    return {"slots": found, "trace": [trace("slots", offered=[s["start"] for s in found])]}


# ---------------------------------------------------------------- draft
def _floor(job: dict) -> tuple[float, str]:
    u = cfg()["user"]
    return (u["min_hourly_rate"], "/hr") if job.get("budget_type") == "hourly" else (u["min_fixed_budget"], " fixed")


def _nice(slot: str) -> str:
    from datetime import datetime
    return datetime.fromisoformat(slot).strftime("%a %d %b, %H:%M")


def _rule_reply(state) -> ReplyDraft:
    intent, job, sl = state["intent"]["intent"], state.get("job") or {}, state.get("slots") or []
    skill = (job.get("skills") or ["your project"])[0]
    if intent == "interview_request":
        times = "; ".join(_nice(s["start"]) for s in sl) or "a time that suits you this week"
        return ReplyDraft(text=f"Thanks, I'd be glad to talk. I'm free at: {times}. Let me know which works "
                               "best and I'll keep it reserved for you.")
    if intent == "negotiation":
        floor, unit = _floor(job)
        return ReplyDraft(text=f"Thanks for being upfront about the budget. My minimum for this kind of work is "
                               f"${floor:,.0f}{unit}, but I'm happy to adjust the scope so it fits: we could start "
                               "with the most important deliverable first. Which part matters most to you?")
    if intent == "question":
        return ReplyDraft(text=f"Thanks for the question. For {skill}, I would start with a short written plan "
                               "on day one so you can confirm the approach, then deliver the first working piece "
                               "early for your feedback. Happy to walk you through the details here.")
    return ReplyDraft(text="Thanks for your message! Let me know if you have any questions about the "
                           "proposal; I'm happy to help here.")


async def draft_reply(state, config: RunnableConfig):
    if budget_exceeded(state):
        return {"status": "needs_attention", "errors": ["token budget exceeded"], "trace": [trace("draft_reply", stopped="budget")]}
    store, user = current_store(), user_of(config)
    rules = await style_rules(store, user)
    if state["intent"]["intent"] == "scam_signal":       # fixed safe reply, no LLM to manipulate
        return {"draft": {"text": SAFE_SCAM_REPLY},
                "trace": [trace("draft_reply", intent="scam_signal", model="template")]}
    floor, unit = _floor(state.get("job") or {})
    history = "\n".join(f"{m['sender']}: {m['text'][:300]}" for m in state.get("history", [])[:-1])
    user_msg = "\n\n".join(filter(None, [
        f"JOB: {(state.get('job') or {}).get('title', 'unknown')}",
        f"INTENT: {state['intent']['intent']} - {state['intent'].get('summary', '')}",
        f"EARLIER MESSAGES:\n{history}" if history else "",
        "NEWEST CLIENT MESSAGE:\n" + fence_message(state["incoming"]["text"]),
        f"FLOOR: never below ${floor:,.0f}{unit}",
        ("SLOTS (offer all): " + "; ".join(_nice(s["start"]) for s in state.get("slots", []))) if state.get("slots") else "",
        ("STYLE RULES:\n" + "\n".join(f"- {r['rule']}" for r in rules)) if rules else "",
    ]))
    draft, info = await structured("liaison", ReplyDraft, prompt("liaison"), user_msg, lambda: _rule_reply(state))
    text = apply_style(draft.text, rules) if info["fallback_used"] else draft.text
    return {"draft": {"text": text}, "tokens": info["tokens"],
            "trace": [trace("draft_reply", style_rules=len(rules), **info)]}


# ---------------------------------------------------------------- check + preview
async def compliance_msg(state, config=None):
    c = cfg()["compliance"]
    text, violations = check(state["draft"]["text"], c["rules"])
    floor, _ = _floor(state.get("job") or {})
    kept = []
    for s in sentences(text):                            # never quote a price below the floor
        low = [float(x.replace(",", "")) for x in re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)", s)
               if float(x.replace(",", "")) < floor]
        if low:
            violations.append(f"below_floor: \"{s[:80]}\"")
        else:
            kept.append(s)
    text = " ".join(kept)
    blocked = not text.strip() or len(violations) > c["block_if_removed_more_than"]
    out = {"draft": {"text": text}, "compliance": {"passed": not violations, "blocked": blocked, "violations": violations},
           "trace": [trace("compliance_msg", violations=len(violations), blocked=blocked)]}
    if blocked:
        out["status"] = "needs_attention"
        out["errors"] = ["compliance blocked the reply: " + "; ".join(violations[:3])]
    return out


async def preview_msg(state, config: RunnableConfig):
    res = await toolbox(config).call("liaison_preview", "send_message", client_id=state["client_id"],
                                     job_id=state.get("job_id"), text=state["draft"]["text"],
                                     idempotency_key=_key(state, config), dry_run=True)   # dry_run forced here
    return {"preview": res, "status": "awaiting_approval", "trace": [trace("preview_msg", dry_run=True)]}


# ---------------------------------------------------------------- human approval + send
async def approve_msg(state, config: RunnableConfig):
    payload = {"client_id": state["client_id"], "job": {k: (state.get("job") or {}).get(k) for k in ("job_id", "title")},
               "incoming": state["incoming"], "history": state.get("history", []), "intent": state["intent"],
               "draft": state["draft"], "slots": state.get("slots", []), "compliance": state.get("compliance"),
               "dry_run": state.get("preview")}
    decision = MessageApproval(**interrupt(payload))      # graph pauses here until the human answers
    out = {"approval": decision.model_dump(), "trace": [trace("approve_msg", action=decision.action)]}
    if decision.action == "edit" and decision.text:
        before = state["draft"]["text"]
        out["draft"] = {"text": decision.text}
        out["edits"] = [{"before": before, "after": decision.text}]
        store = current_store()
        if store is not None:                              # edits feed style memory via the promotion rule
            promoted = await record_edit(store, user_of(config), state.get("job_id") or state["client_id"],
                                         before, decision.text)
            out["trace"].append(trace("style_memory", promoted=promoted))
    elif decision.action == "reject":
        out["status"] = "rejected"
        out["handled"] = _answered(state)
    return out


def _answered(state) -> list[str]:
    """The newest message and any older unanswered client messages it covered."""
    ids = {m["message_id"] for m in state.get("history", []) if m["sender"] == "client"} | {state["incoming"]["message_id"]}
    return sorted(ids - set(state.get("handled") or []))


def route_after_approve(state) -> str:
    return {"approve": "send_msg", "edit": "compliance_msg", "reject": "end"}[state["approval"]["action"]]


async def send_msg(state, config: RunnableConfig):
    """Runs only after approval. Idempotency keys come from the thread + message id: a crash and resume
    re-sends the SAME request, so the client never gets the message twice."""
    tb, key = toolbox(config), _key(state, config)
    try:
        res = await tb.call("liaison_send", "send_message", client_id=state["client_id"], job_id=state.get("job_id"),
                            text=state["draft"]["text"], idempotency_key=key, dry_run=False)
        hold = None
        slot = (state.get("approval") or {}).get("slot")
        if state["intent"]["intent"] == "interview_request" and slot:
            hold = await tb.call("liaison_send", "create_hold", start=slot, idempotency_key=f"{key}-hold",
                                 title=f"Interview: {(state.get('job') or {}).get('title', state['client_id'])}"[:200],
                                 duration_min=cfg()["liaison"]["slot_minutes"])
    except ToolCallError as e:
        if "marketplace_unavailable" in str(e):
            raise                                          # stay paused here; resume later (nothing lost)
        return {"status": "needs_attention", "errors": [f"send: {e}"], "trace": [trace("send_msg", error=str(e))]}
    return {"sent": {**res, "hold": hold}, "status": "sent", "handled": _answered(state),
            "trace": [trace("send_msg", message_id=res.get("message_id"), hold=(hold or {}).get("hold_id"))]}
