"""Conversation graph (C1): one thread per client conversation (thread id = conv-<client_id>).

read_messages -> (nothing new: end)
  -> classify intent (question | negotiation | interview_request | scam_signal | other)
  -> interview_request: free calendar slots -> draft_reply
  -> draft_reply (scam_signal: fixed safe reply, no LLM)
  -> compliance_msg (block -> end) -> preview_msg (dry_run) -> HUMAN APPROVAL (interrupt)
  -> approve: send_msg (+ tentative calendar hold) | edit: compliance again (+ style memory) | reject: end

Run it again on the same thread when the client writes again: answered message ids are kept in
`handled`, so a message is never answered twice.
"""
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agent.nodes.liaison import (
    approve_msg,
    classify,
    compliance_msg,
    draft_reply,
    preview_msg,
    read_messages,
    route_after_approve,
    route_after_classify,
    route_after_read,
    send_msg,
    slots,
)
from agent.state import ConvState


def build_conversation_graph(checkpointer=None, store=None):
    retry = RetryPolicy(max_attempts=2)
    g = StateGraph(ConvState)
    g.add_node("read_messages", read_messages, retry_policy=retry)
    g.add_node("classify", classify)
    g.add_node("slots", slots, retry_policy=retry)
    g.add_node("draft_reply", draft_reply)
    g.add_node("compliance_msg", compliance_msg)
    g.add_node("preview_msg", preview_msg, retry_policy=retry)
    g.add_node("approve_msg", approve_msg)
    g.add_node("send_msg", send_msg)

    g.add_edge(START, "read_messages")
    g.add_conditional_edges("read_messages", route_after_read, {"classify": "classify", "end": END})
    g.add_conditional_edges("classify", route_after_classify, ["slots", "draft_reply"])
    g.add_edge("slots", "draft_reply")
    g.add_conditional_edges("draft_reply", lambda s: END if s.get("status") == "needs_attention" else "compliance_msg",
                            ["compliance_msg", END])
    g.add_conditional_edges("compliance_msg", lambda s: END if s["compliance"]["blocked"] else "preview_msg",
                            ["preview_msg", END])
    g.add_edge("preview_msg", "approve_msg")
    g.add_conditional_edges("approve_msg", route_after_approve, {"send_msg": "send_msg", "compliance_msg": "compliance_msg", "end": END})
    g.add_edge("send_msg", END)
    return g.compile(checkpointer=checkpointer, store=store)
