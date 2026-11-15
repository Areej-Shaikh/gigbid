### R&D question A: tool granularity (model=openai/gpt-oss-20b, temperature 0; PARTIAL (daily token limit): 28 of 40 tasks completed under all three sets)

Paired on the 28 tasks (of 40) that all three tool sets completed. One forced tool call per task.

| Tool set | Tools | Tool-selection accuracy | Argument accuracy | Tokens per task | Input tokens per task |
|---|---|---|---|---|---|
| fine | 13 | 26/28 = 93% | 26/28 = 93% | 1344 | 1221 |
| coarse | 3 | 26/28 = 93% | 25/28 = 89% | 727 | 521 |
| rewritten | 13 | 27/28 = 96% | 27/28 = 96% | 1562 | 1476 |

**Errors (tool or arguments wrong)**

| Task | Set | Gold tool | Picked | Arguments given |
|---|---|---|---|---|
| tool-23 | coarse | search_evidence | portfolio_read.search_evidence | {"k": 10, "outcomes": null, "requirement": "churn prediction", "since": null, "types": ["case study"]} |
| tool-24 | coarse | search_evidence | marketplace_read.list_proposals | {} |
| tool-24 | fine | search_evidence | list_proposals | {"": ""} |
| tool-24 | rewritten | search_evidence | list_proposals | {"": ""} |
| tool-25 | coarse | search_evidence | marketplace_read.search_jobs | {"limit": 10, "offset": 0, "query": "FastAPI"} |
| tool-25 | fine | search_evidence | get_client_history | {"client_id": "unknown"} |
