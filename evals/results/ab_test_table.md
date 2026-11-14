### X2 proposal A/B test in GigSim (LLM profile=fake; RAG_VARIANT=bm25; 180 dev jobs per arm)

| | evidence_first | plan_first |
|---|---|---|
| Realistic A/B (hash split) reply rate | 53/77 = 68.8% [58%-78%] | 36/65 = 55.4% [43%-67%] |
| Paired (same jobs, both arms) reply rate | 87/142 = 61.3% [53%-69%] | 77/142 = 54.2% [46%-62%] |
| Interview rate (paired) | 39/142 | 30/142 |
| Avg letter words (paired) | 114 | 105 |

- Realistic split: Fisher exact p = 0.118, two-proportion z = 1.65 (p = 0.099). With 65 jobs per arm, the smallest difference detectable with 80% power is about 24% (absolute).
- Paired: 34 jobs got a reply only with evidence_first, 24 only with plan_first; exact McNemar p = 0.237.
