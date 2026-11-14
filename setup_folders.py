import os

folders = [
    "apps/web", "apps/api/routers", "apps/api/auth", "apps/api/schemas",
    "agent/graphs", "agent/nodes", "agent/prompts", "agent/memory",
    "rag/ingest", "rag/index", "rag/variants",
    "mcp_servers/portfolio/tests", "mcp_servers/marketplace/adapters",
    "mcp_servers/marketplace/tests", "mcp_servers/workspace",
    "worker", "gigsim", "data/personas", "data/policy_pack", "data/processed",
    "evals/datasets", "evals/runners", "evals/results",
    "tests/unit", "tests/integration", "tests/contract",
    "infra/docker", ".github/workflows", "docs/adr", "docs/images",
]
for f in folders:
    os.makedirs(f, exist_ok=True)
    open(os.path.join(f, ".gitkeep"), "a").close()  # so Git keeps empty folders

for f in ["Makefile", ".env.example"]:
    open(f, "a").close()
print("Done")
