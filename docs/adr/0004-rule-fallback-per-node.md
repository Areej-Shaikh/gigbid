# ADR 0004: Every LLM node has a deterministic rule-based fallback

**Status:** accepted

## Context
Free LLM tiers have per-minute and per-day limits and occasional malformed JSON. A run that dies halfway
leaves the user with nothing; tests and CI need to run without keys.

## Decision
`agent/llm.py::structured()` takes a fallback function for every node. Order: the node's model (waiting out
per-minute rate limits, one retry on bad JSON) → the fallback model for small nodes → the rule-based result.
`LLM_PROFILE=fake` uses only the rules. Every call records `fallback_used` in the run trace and the span.

## Consequences
+ Runs always finish; tests, CI and an offline demo need no API key; large evaluations can run for free.
− A fallback hides provider failures unless checked. The injection evaluation therefore marks any case whose
  final output came from a fallback as invalid (a template cannot be injected, so it would understate attack success).
