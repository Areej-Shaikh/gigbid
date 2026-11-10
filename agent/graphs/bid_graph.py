"""Bid graph (C1): one thread per job.

intake -> [Job Analyst | Risk Assessor | Fit Matcher] in parallel (Send) -> decide
  -> skip/watch: end
  -> bid: pricing -> writer -> claim verifier -> critic (back to writer at most 2x)
         -> compliance (block -> end) -> preview (dry_run) -> HUMAN APPROVAL (interrupt)
         -> approve: submit | edit: compliance again | reject: end
"""
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent.nodes.analyst import analyst
from agent.nodes.approval import human_approval, preview, route_after_approval, submit
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.decide import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.intake import intake
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState


def fan_out(state):
    if state.get("status") != "running":
        return END
    return [Send("analyst", state), Send("risk", state), Send("fit", state)]


def build_bid_graph(checkpointer=None):
    retry = RetryPolicy(max_attempts=2)
    g = StateGraph(BidState)
    g.add_node("intake", intake, retry_policy=retry)
    g.add_node("analyst", analyst)
    g.add_node("risk", risk_assessor)
    g.add_node("fit", fit_matcher, retry_policy=retry)
    g.add_node("decide", decide)
    g.add_node("pricing", pricing, retry_policy=retry)
    g.add_node("writer", writer)
    g.add_node("verifier", verifier)
    g.add_node("critic", critic)
    g.add_node("compliance", compliance)
    g.add_node("preview", preview, retry_policy=retry)
    g.add_node("human_approval", human_approval)
    g.add_node("submit", submit)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk", "fit", END])
    g.add_edge(["analyst", "risk", "fit"], "decide")          # waits for all three branches
    g.add_conditional_edges("decide", lambda s: "pricing" if s["status"] == "running" else END, ["pricing", END])
    g.add_edge("pricing", "writer")
    g.add_conditional_edges("writer", lambda s: END if s.get("status") == "needs_attention" else "verifier", ["verifier", END])
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", route_after_critic, {"writer": "writer", "compliance": "compliance", "end": END})
    g.add_conditional_edges("compliance", lambda s: END if s["compliance"]["blocked"] else "preview", ["preview", END])
    g.add_edge("preview", "human_approval")
    g.add_conditional_edges("human_approval", route_after_approval, {"submit": "submit", "compliance": "compliance", "end": END})
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer)
