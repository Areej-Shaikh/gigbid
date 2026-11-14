# ADR 0001: An explicit LangGraph state graph, not a free-form agent loop

**Status:** accepted

## Context
A proposal is spent money (Connects) and the freelancer's reputation. The flow has fixed safety steps
(verify claims, check policy, wait for a human) that must happen in order, every time.

## Decision
Model each flow as an explicit `StateGraph` with one node per agent, typed handoffs (Pydantic models in
`agent/handoffs.py`), conditional edges for decisions, and `interrupt()` for human approval.
LLMs work inside nodes; they do not choose the next step.

## Consequences
+ Safety steps cannot be skipped by a model; every run is inspectable node by node and replayable from checkpoints.
+ Parallel analysis with `Send`, bounded loops (critic revisions ≤ 2), and a recursion limit come for free.
− Less flexible than a ReAct agent for unexpected tasks; new behaviour needs a new node or edge.
