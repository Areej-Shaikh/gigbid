### R&D question C: one ReAct agent vs prebuilt supervisor vs hand-built graph (models=openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b (one per job, same for all three architectures) via open profile; 30 stratified dev jobs; RAG_VARIANT=bm25; PARTIAL (daily token limit))

Paired comparison on the 0 jobs where all three architectures produced a valid run (1 jobs attempted). Within each job all three architectures use the same model.

| Metric | (a) ReAct agent | (b) Supervisor | (c) GigBid graph |
|---|---|---|---|

**Decision accuracy by job type**

| Job type | n | (a) ReAct | (b) Supervisor | (c) Graph |
|---|---|---|---|---|

Invalid runs excluded (provider errors, LLM fallbacks, or no structured answer): {'graph': 0, 'react': 0, 'supervisor': 0}.
