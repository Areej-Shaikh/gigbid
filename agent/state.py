"""Bid graph state (C2). Three things are kept apart:
  - STATE (fields below): what this job needs right now
  - EXECUTION TRACE (`trace`): every tool call / node result, append-only, for audit and debugging
  - LONG-TERM MEMORY: NOT here; only promoted knowledge goes to the LangGraph store (agent/memory/)
Fields written by parallel branches are separate keys, or use reducers (operator.add).
"""
import operator
from typing import Annotated, Any, TypedDict


class BidState(TypedDict, total=False):
    job_id: str
    job: dict[str, Any]
    client: dict[str, Any]
    # parallel branches: each writes its own key
    job_spec: dict
    risk: dict
    fit: dict
    evidence: Annotated[dict[str, dict], lambda a, b: {**(a or {}), **(b or {})}]
    decision: dict
    price: dict
    draft: dict                 # {"cover_letter", "screening_answers"}
    verification: dict
    critique: dict
    revisions: int
    compliance: dict
    preview: dict
    approval: dict
    edits: Annotated[list[dict], operator.add]
    submission: dict
    status: str                 # running | skipped | watch | awaiting_approval | submitted | rejected | needs_attention | dead_letter
    # bookkeeping (reducers so parallel nodes can all append)
    trace: Annotated[list[dict], operator.add]
    tokens: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]


class ConvState(TypedDict, total=False):
    """Conversation graph state: one thread per client conversation (thread id = conv-<client_id>)."""
    client_id: str
    job_id: str | None
    job: dict[str, Any]
    history: list[dict]          # the conversation so far (client + freelancer messages)
    incoming: dict               # the newest client message not handled yet
    intent: dict
    slots: list[dict]
    draft: dict                  # {"text"}
    compliance: dict
    preview: dict
    approval: dict
    sent: dict
    handled: Annotated[list[str], operator.add]     # message ids already answered (never answer twice)
    edits: Annotated[list[dict], operator.add]
    status: str                  # running | no_new_messages | awaiting_approval | sent | rejected | needs_attention
    trace: Annotated[list[dict], operator.add]
    tokens: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]
