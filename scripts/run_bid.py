"""Run the bid graph on one job from the terminal, with approval in the terminal (until the web UI exists).

  python scripts/run_bid.py job-00012              # new run (thread id = job id)
  python scripts/run_bid.py job-00012 --resume     # continue a paused/crashed thread
  python scripts/run_bid.py --graph                # save both graph diagrams to docs/images/*.mmd

Needs GigSim running on :8001. Checkpoints are saved in data/processed/checkpoints.sqlite,
so you can close the terminal while it waits for approval and resume later.
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, so "agent" imports work
load_dotenv()

from langgraph.types import Command  # noqa: E402

from agent.config import cfg  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.mcp_client import open_toolbox  # noqa: E402
from agent.persistence import backend, open_persistence  # noqa: E402


def show(payload: dict) -> None:
    j, p = payload["job"], payload["price"]
    print("\n" + "=" * 70)
    print(f"APPROVAL NEEDED: {j['title']}  ({j['job_id']})")
    print(f"Risk: {payload['risk']['level']} {payload['risk']['flags']}")
    print("Fit matrix: " + ", ".join(f"{r['requirement']}={'OK' if r['covered'] else 'GAP'}" for r in payload["fit_matrix"]))
    print(f"Price: ${p['amount']} ({p['budget_type']}) | " + " | ".join(p["rationale"]))
    print(f"Dry run: {payload['dry_run']['connects_cost']} Connects, balance after {payload['dry_run']['connects_balance_after']}")
    v = payload.get("verification") or {}
    print(f"Claims checked: {len(v.get('checks', []))}, unsupported removed: {v.get('unsupported_before', 0)}")
    print("-" * 70 + "\n" + payload["draft"]["cover_letter"])
    for q, a in zip(payload["job"].get("screening_questions") or [], payload["draft"]["screening_answers"]):
        print(f"\nQ: {q}\nA: {a}")
    print("-" * 70 + "\nEvidence:")
    for i, e in payload["evidence"].items():
        print(f"  [{i}] {e['title']}")


def ask() -> dict:
    while True:
        a = input("\n[a]pprove / [e]dit / [r]eject ? ").strip().lower()
        if a == "a":
            return {"action": "approve"}
        if a == "r":
            return {"action": "reject", "reason": input("Reason: ")}
        if a == "e":
            return {"action": "edit", "cover_letter": input("Paste the new cover letter (one line):\n")}


async def main():
    if "--graph" in sys.argv:          # both graphs rendered from code (C1)
        from agent.graphs.conversation_graph import build_conversation_graph
        for name, g in (("bid_graph", build_bid_graph()), ("conversation_graph", build_conversation_graph())):
            out = Path(f"docs/images/{name}.mmd")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(g.get_graph().draw_mermaid(), encoding="utf-8")
            print(f"saved {out}")
        return
    job_id = sys.argv[1]
    print(f"LLM profile: {cfg()['profile']} | persistence: {backend()}")
    async with open_persistence() as (saver, store), open_toolbox() as tb:
        graph = build_bid_graph(saver, store)
        conf = {"configurable": {"toolbox": tb, "thread_id": job_id}, "recursion_limit": cfg()["budgets"]["max_steps"]}
        state = await graph.aget_state(conf)
        if "--resume" in sys.argv or state.next:
            print(f"Resuming thread {job_id} at {state.next}")
            out = None if not state.tasks or not state.tasks[0].interrupts else "interrupt"
            if out == "interrupt":
                payload = state.tasks[0].interrupts[0].value
                show(payload)
                result = await graph.ainvoke(Command(resume=ask()), conf)
            else:
                result = await graph.ainvoke(None, conf)
        else:
            result = await graph.ainvoke({"job_id": job_id}, conf)
        while "__interrupt__" in result:
            show(result["__interrupt__"][0].value)
            result = await graph.ainvoke(Command(resume=ask()), conf)
        print("\n" + "=" * 70)
        print(f"STATUS: {result.get('status')}")
        if result.get("decision"):
            print(f"Decision: {result['decision']['action']}: {'; '.join(result['decision']['reasons'])}")
        if result.get("submission"):
            print(f"Submitted: {json.dumps(result['submission'])}")
        if result.get("errors"):
            print(f"Errors: {result['errors']}")
        print(f"Nodes: {' -> '.join(t['node'] for t in result['trace'])}")
        print(f"Tokens: {result.get('tokens', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
