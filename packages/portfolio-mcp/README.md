# gigbid-portfolio-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that lets an AI assistant (Claude Desktop, Cursor,
VS Code, or any MCP host) **search a freelancer's portfolio and cite real evidence**: case studies, repositories,
client reviews, past proposals and the CV.

Use it to answer screening questions or write proposals where every claim points to something you actually did.
It is the portfolio server from [GigBid](https://github.com/Areej-Shaikh/gigbid), a multi-agent freelancer copilot.

## Install and run

```bash
pip install gigbid-portfolio-mcp
gigbid-portfolio-mcp                       # serves the bundled sample portfolio over stdio
```

Or without installing, with [uv](https://docs.astral.sh/uv/):

```bash
uvx gigbid-portfolio-mcp
```

Point it at your own portfolio:

```bash
PORTFOLIO_DIR=/path/to/my-portfolio gigbid-portfolio-mcp          # PowerShell: $env:PORTFOLIO_DIR="C:\path"
```

### Claude Desktop / Cursor / VS Code

Add to the host's MCP configuration (Claude Desktop: `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "uvx",
      "args": ["gigbid-portfolio-mcp"],
      "env": { "PORTFOLIO_DIR": "/path/to/my-portfolio" }
    }
  }
}
```

Leave out `env` to try it on the sample portfolio first.

## What it offers

| Kind | Name | What it does |
|---|---|---|
| Tool | `search_evidence(requirement, k, types, outcomes, since)` | Ranked evidence for one requirement, with type, project, skills, date, client industry and outcome |
| Tool | `get_case_study(evidence_id)` | Full text of one evidence item |
| Tool | `list_skills()` | Skills and how many evidence items back each one |
| Resource | `portfolio://case/{id}` | A case study as Markdown |
| Resource | `portfolio://proposal/{id}` | A past proposal with its outcome |
| Resource | `portfolio://profile` | Headline, rate, skills |
| Prompt | *Answer a screening question from my portfolio* | Grounded answer that cites `[evidence_id]` |
| Prompt | *Find my best proof for a job* | Requirement → strongest evidence table, gaps marked |

All tools are **read-only** (`readOnlyHint: true`, `idempotentHint: true`); the server never writes anywhere.
Retrieval is BM25+ (keyword ranking): no model download, millisecond latency. In GigBid's evaluation it gave better end-to-end bid
decisions than hybrid dense retrieval, even though hybrid had higher recall.

## Portfolio folder format

All parts are optional; use what you have.

```
my-portfolio/
├── cv.md
├── profile.json            {"headline": "...", "hourly_rate": 40, "skills": ["Python", "..."]}
├── case_studies/
│   └── churn-model.md      front matter, then the story (see below)
├── repos/
│   └── my-repo/            README.md and any source files
├── reviews.json            [{"id": "...", "rating": 5, "project": "...", "text": "...", "date": "2026-01-31"}]
└── proposals.json          [{"id": "...", "job_title": "...", "text": "...", "outcome": "replied", "job_skills": [...]}]
```

Case study front matter:

```markdown
---
id: "me-case-01"
title: "Churn prediction for a telecom client"
project: "Churn model"
skills: ["Python", "scikit-learn"]
date: "2026-02-14"
client_industry: "telecom"
outcome: "delivered"
---
Problem, what you built, and the measured result.
```

## Privacy

Everything stays on your machine: the server reads local files only and makes no network calls.
The bundled sample portfolio is synthetic.

## Development

```bash
pip install -e ".[test]"
pytest
```

License: MIT.
