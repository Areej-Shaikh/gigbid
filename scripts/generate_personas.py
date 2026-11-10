"""Generate 3 SYNTHETIC freelancer personas (portfolio corpus for RAG).

Usage:  python scripts/generate_personas.py
Output: data/personas/<persona_id>/
          profile.json          rates, skills, headline
          cv.md                 CV
          case_studies/*.md     ~18 case studies (YAML front matter + text)
          repos/<name>/README.md + main code file
          reviews.json          client reviews
          proposals.json        ~150 past proposals labelled won / replied / ignored

Deliberately "messy" like real portfolios (the assignment wants RAG to be hard):
  - the same project appears 3 ways (case study, repo README, past proposal)
  - some skills are only IMPLIED in the text, not listed in tags
  - proposal outcome depends on specificity, not on wording style
Everything here is synthetic: source = "synthetic".
"""
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
OUT = Path("data/personas")

INDUSTRIES = ["fintech", "healthcare", "e-commerce", "education", "logistics", "real estate", "marketing", "SaaS"]

PERSONAS = {
    "ai_ml_engineer": {
        "name": "Sara Malik (synthetic)", "headline": "AI/ML Engineer: LLM apps, RAG, classical ML",
        "hourly_rate": 35, "min_project": 300, "years": 4,
        "skills": ["Python", "PyTorch", "scikit-learn", "LangChain", "LangGraph", "RAG", "FastAPI", "Docker",
                   "Postgres", "pgvector", "Hugging Face", "OpenAI API", "NLP", "MLflow", "Celery"],
        "projects": [
            ("Contract Q&A assistant", "RAG chatbot answering questions over {n} legal contracts with citations",
             ["RAG", "LangChain", "FastAPI", "pgvector"], "Celery workers re-index new PDFs every night",
             "answer accuracy rose from {a}% to {b}% on a 200-question test set"),
            ("Churn prediction model", "gradient-boosted churn model on {n}k customer records",
             ["scikit-learn", "Python", "MLflow"], "SHAP plots explained the top drivers to the sales team",
             "recall on churners improved from {a}% to {b}%"),
            ("Support ticket classifier", "fine-tuned a small transformer to route {n}k support tickets",
             ["Hugging Face", "PyTorch", "NLP"], "deployed behind a Docker container on a CPU-only VM",
             "manual triage time fell by {a}%"),
            ("Invoice data extraction", "LLM pipeline extracting fields from {n} scanned invoices",
             ["OpenAI API", "Python", "FastAPI"], "Pydantic schemas validated every extracted field",
             "field-level accuracy reached {b}% with a {a}% cost cut vs manual entry"),
            ("Multi-agent research assistant", "LangGraph agent team that drafts market reports from {n} sources",
             ["LangGraph", "LangChain", "Python"], "a critic node sends weak drafts back at most twice",
             "report drafting time dropped from {a} hours to {b} minutes"),
            ("Demand forecasting", "weekly demand forecasts for {n} SKUs",
             ["Python", "scikit-learn", "Postgres"], "backtested on two years of sales history",
             "forecast error (MAPE) fell from {a}% to {b}%"),
        ],
    },
    "fullstack_developer": {
        "name": "Bilal Khan (synthetic)", "headline": "Full-Stack Web Developer: Next.js, Node, Django",
        "hourly_rate": 28, "min_project": 200, "years": 5,
        "skills": ["JavaScript", "TypeScript", "React", "Next.js", "Node.js", "Express", "Django", "Postgres",
                   "MongoDB", "Tailwind CSS", "Stripe", "AWS", "Docker", "REST API", "GraphQL"],
        "projects": [
            ("Multi-vendor marketplace", "Next.js marketplace with {n} vendors and Stripe Connect payouts",
             ["Next.js", "Stripe", "Postgres", "TypeScript"], "webhooks reconcile payouts every hour",
             "checkout conversion rose from {a}% to {b}%"),
            ("Clinic booking system", "Django booking app for {n} clinics with SMS reminders",
             ["Django", "Postgres", "REST API"], "role-based access for doctors, staff and patients",
             "no-shows dropped by {a}%"),
            ("SaaS admin dashboard", "React dashboard showing live metrics for {n} customer accounts",
             ["React", "TypeScript", "Tailwind CSS", "GraphQL"], "charts update over WebSockets",
             "page load time fell from {a}s to {b}s"),
            ("Shopify-to-ERP sync", "Node.js service syncing {n} products between Shopify and an ERP",
             ["Node.js", "Express", "MongoDB"], "a retry queue handles API rate limits",
             "stock mismatches fell by {a}%"),
            ("Learning platform", "course platform with video, quizzes and {n} students",
             ["Next.js", "Node.js", "AWS"], "videos are served from S3 through CloudFront",
             "monthly hosting cost fell by {a}%"),
            ("Real-estate listings site", "listings site with map search over {n} properties",
             ["React", "Express", "Postgres"], "PostGIS powers radius search",
             "search response time dropped from {a}ms to {b}ms"),
        ],
    },
    "data_analyst": {
        "name": "Ayesha Raza (synthetic)", "headline": "Data Analyst: SQL, Power BI, Python, dbt",
        "hourly_rate": 22, "min_project": 150, "years": 3,
        "skills": ["SQL", "Python", "Pandas", "Power BI", "Tableau", "Excel", "dbt", "Airflow", "Postgres",
                   "BigQuery", "Google Data Studio", "Statistics", "A/B testing", "Data Visualization", "ETL"],
        "projects": [
            ("Sales performance dashboard", "Power BI dashboard over {n}k sales rows for regional managers",
             ["Power BI", "SQL", "Data Visualization"], "row-level security per region",
             "weekly reporting time fell from {a} hours to {b} minutes"),
            ("Marketing attribution analysis", "multi-touch attribution across {n} campaigns",
             ["Python", "Pandas", "Statistics"], "results presented in a Google Data Studio report",
             "budget shifted to channels with {a}% higher ROI"),
            ("dbt warehouse rebuild", "rebuilt {n} messy tables into tested dbt models in BigQuery",
             ["dbt", "BigQuery", "SQL"], "an Airflow DAG runs the models every morning",
             "data-quality incidents fell by {a}%"),
            ("Pricing A/B test", "designed and analysed a pricing experiment with {n}k users",
             ["A/B testing", "Statistics", "Python"], "power analysis decided the sample size up front",
             "the winning price lifted revenue per user by {a}%"),
            ("Inventory Excel automation", "automated a {n}-sheet inventory workbook",
             ["Excel", "Python", "ETL"], "Power Query replaced manual copy-paste",
             "month-end close took {a}% less time"),
            ("Customer segmentation", "RFM segmentation of {n}k customers",
             ["Python", "Pandas", "Tableau"], "segments were pushed to the CRM for targeted email",
             "email click-through rose from {a}% to {b}%"),
        ],
    },
}

GENERIC_OPENINGS = ["Dear Sir/Madam, I am very passionate about this job and I am the best fit.",
                    "Hello, I have read your job post and I can do this job perfectly.",
                    "Hi there! I am a hardworking professional with many years of experience."]
JOB_PHRASES = ["Need help with", "Looking for an expert in", "Build a", "Fix and improve our", "Urgent:"]


def nums():
    a = random.randint(10, 60)
    return {"n": random.choice([12, 40, 85, 150, 300, 1200]), "a": a, "b": min(99, a + random.randint(8, 35))}


def make_case_studies(pid, p):
    cases = []
    for i in range(18):
        title, what, skills, detail, result = p["projects"][i % len(p["projects"])]
        industry = random.choice(INDUSTRIES)
        v = nums()
        # nums() gives b > a; a "fell/dropped from {a}X to {b}X" result (same unit) must go DOWN
        if re.search(r"(fell|dropped) from \{a\}(\S*) to \{b\}\2", result):
            v["a"], v["b"] = v["b"], v["a"]
        d = date(2023, 1, 1) + timedelta(days=random.randint(0, 900))
        # every 3rd case: skill only IMPLIED in text, not in tags
        tags = skills if i % 3 else skills[:-1]
        variant = i // len(p["projects"])
        style = ["Client problem: ", "Context. ", "For a {ind} company, "][variant].format(ind=industry)
        text = (f"{style}a {industry} client needed a {what.format(**v)}. "
                f"I designed and built it end to end. {detail.capitalize()}. "
                f"Main tools: {', '.join(skills)}. Result: {result.format(**v)}. "
                f"Delivered in {random.randint(2, 8)} weeks.")
        cases.append({"id": f"{pid}-case-{i + 1:02d}", "title": f"{title} ({industry})", "project": title,
                      "skills": tags, "date": d.isoformat(), "client_industry": industry,
                      "outcome": "delivered", "text": text})
    return cases


def write_case(path, c):
    fm = {k: c[k] for k in ("id", "title", "project", "skills", "date", "client_industry", "outcome")}
    fm["source"] = "synthetic"
    lines = ["---"] + [f"{k}: {json.dumps(v)}" for k, v in fm.items()] + ["---", "", f"# {c['title']}", "", c["text"], ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def make_repos(pid, p, folder):
    repos = []
    for title, what, skills, detail, _ in p["projects"][:5]:
        name = title.lower().replace(" ", "-").replace("/", "-")
        d = folder / name
        d.mkdir(parents=True, exist_ok=True)
        # README is vague on purpose; the code shows the real stack
        readme = (f"# {name}\n\n{title}: a side project.\n\n## Run\n\n```\ndocker compose up\n```\n\n"
                  f"_Synthetic repository generated for GigBid._\n")
        code = (f"# {title}: main module\n# Stack: {', '.join(skills)}\n# {detail}\n\n"
                f"def main():\n    \"\"\"{what.format(n='N')}\"\"\"\n    ...\n")
        (d / "README.md").write_text(readme, encoding="utf-8")
        (d / "main.py").write_text(code, encoding="utf-8")
        repos.append({"id": f"{pid}-repo-{name}", "project": title, "skills": skills})
    return repos


def make_reviews(pid, cases):
    good = ["Excellent communication and delivered ahead of schedule.", "Clear explanations, solid code, will hire again.",
            "Understood our business problem quickly.", "Great work, the results speak for themselves."]
    ok = ["Good work but needed a few extra revisions.", "Delivered, though a bit later than planned."]
    reviews = []
    for c in random.sample(cases, 10):
        stars = random.choice([5, 5, 5, 4, 4, 3])
        reviews.append({"id": f"{pid}-review-{len(reviews) + 1:02d}", "project": c["project"],
                        "case_id": c["id"], "client_industry": c["client_industry"], "rating": stars,
                        "text": random.choice(good if stars >= 4 else ok), "date": c["date"], "source": "synthetic"})
    return reviews


def make_proposals(pid, p, cases):
    proposals = []
    all_skills = p["skills"]
    for i in range(150):
        job_skills = random.sample(all_skills, 2) + ([random.choice(["Java", "PHP", "Flutter", "Rust", "SAP"])]
                                                      if random.random() < 0.3 else [])
        job_title = f"{random.choice(JOB_PHRASES)} {' / '.join(job_skills)} project"
        industry = random.choice(INDUSTRIES)
        matching = [c for c in cases if set(c["skills"]) & set(job_skills)]
        cites = random.random() < 0.6 and matching
        generic = random.random() < 0.35
        opening = (random.choice(GENERIC_OPENINGS) if generic
                   else f"Hi, your {industry} project needs {job_skills[0]}, which I use every week.")
        body = opening + " "
        cited = []
        if cites:
            c = random.choice(matching)
            cited = [c["id"]]
            body += f"Recently I built a {c['project'].lower()} for a {c['client_industry']} client: {c['text'].split('Result: ')[1].split('.')[0]}. "
        body += f"I can start this week and keep you updated daily. My rate is ${p['hourly_rate']}/hr."
        # hidden outcome model: specificity + skill fit matter, wording style matters a bit
        fit = len(set(job_skills) & set(all_skills)) / len(job_skills)
        score = 0.15 + 0.35 * bool(cites) + 0.3 * fit - 0.2 * generic + random.uniform(-0.15, 0.15)
        outcome = "won" if score > 0.75 else "replied" if score > 0.5 else "ignored"
        d = date(2023, 1, 1) + timedelta(days=random.randint(0, 1000))
        proposals.append({"id": f"{pid}-prop-{i + 1:03d}", "job_title": job_title, "job_skills": job_skills,
                          "client_industry": industry, "text": body, "cited_evidence": cited,
                          "bid": p["hourly_rate"] + random.randint(-5, 10), "date": d.isoformat(),
                          "outcome": outcome, "source": "synthetic"})
    return proposals


def make_cv(p, cases):
    lines = [f"# {p['name']}", "", f"**{p['headline']}**", "",
             f"{p['years']} years of freelance experience. Hourly rate: ${p['hourly_rate']}.", "",
             "## Skills", "", ", ".join(p["skills"]), "", "## Selected projects", ""]
    for c in cases[:6]:
        lines.append(f"- **{c['project']}** ({c['client_industry']}, {c['date'][:4]}): {c['text'].split('. ')[0]}.")
    lines += ["", "## Education", "", "BS Computer Science (synthetic)", "", "_Synthetic CV generated for GigBid._", ""]
    return "\n".join(lines)


def main():
    for pid, p in PERSONAS.items():
        base = OUT / pid
        (base / "case_studies").mkdir(parents=True, exist_ok=True)
        cases = make_case_studies(pid, p)
        for c in cases:
            write_case(base / "case_studies" / f"{c['id']}.md", c)
        make_repos(pid, p, base / "repos")
        (base / "cv.md").write_text(make_cv(p, cases), encoding="utf-8")
        (base / "reviews.json").write_text(json.dumps(make_reviews(pid, cases), indent=1), encoding="utf-8")
        props = make_proposals(pid, p, cases)
        (base / "proposals.json").write_text(json.dumps(props, indent=1), encoding="utf-8")
        profile = {"persona_id": pid, "name": p["name"], "headline": p["headline"], "hourly_rate": p["hourly_rate"],
                   "minimum_project_budget": p["min_project"], "skills": p["skills"], "source": "synthetic"}
        (base / "profile.json").write_text(json.dumps(profile, indent=1), encoding="utf-8")
        counts = {o: sum(x["outcome"] == o for x in props) for o in ("won", "replied", "ignored")}
        print(f"{pid}: {len(cases)} case studies, 5 repos, 10 reviews, {len(props)} proposals {counts}")


if __name__ == "__main__":
    main()
