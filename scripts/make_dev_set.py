"""Build the labelled DEV set for evaluation (synthetic, generated from the persona projects).

Usage:  python scripts/make_dev_set.py      -> evals/datasets/dev_jobs.json

Per persona: for each of its 6 projects, 8 job posts in 4 styles x 2 phrasings
  explicit  - names the project and the tools        (easy for keyword search)
  vague     - only the client's pain, no tools          (needs meaning, not keywords)
  synonym   - different words for the same thing         (embeddings should help)
  multi     - two needs in one post                      (requirement decomposition should help)
plus off-niche jobs (another persona's work: gold = no evidence, should SKIP)
plus scam jobs (in-niche text + scam signals: should SKIP, scam = true).
Gold labels: relevant evidence ids with grades (case study 2, repo/review 1), bid/skip, scam, fair price band.
"""
import json
import random
from pathlib import Path

random.seed(11)
ROOT = Path("data/personas")
OUT = Path("evals/datasets/dev_jobs.json")

# client-language descriptions of each project: (pain, synonym phrasing)
CLIENT = {
    "Contract Q&A assistant": ("our lawyers waste hours searching old agreements for specific clauses",
                               "a tool to chat with our document archive where every answer shows its source"),
    "Churn prediction model": ("too many subscribers cancel and we never know who will leave next",
                               "predict which customers are about to stop paying so sales can call them first"),
    "Support ticket classifier": ("support requests get sent to the wrong team by hand every morning",
                                  "automatically tag incoming help-desk emails by topic and urgency"),
    "Invoice data extraction": ("our staff type supplier bill details into the accounting system manually",
                                "pull totals, dates and vendor names out of scanned bills into structured records"),
    "Multi-agent research assistant": ("analysts spend days writing market summaries from many sources",
                                       "a team of AI agents that drafts reports and reviews its own work"),
    "Demand forecasting": ("we keep running out of stock on some items and overstocking others",
                           "estimate next week's sales for each product so purchasing can plan"),
    "Multi-vendor marketplace": ("we want independent sellers to list products and get paid automatically",
                                 "an online store with many sellers and split payouts to each one"),
    "Clinic booking system": ("patients miss appointments and all booking is done over the phone",
                              "online appointment scheduling for doctors with text reminders"),
    "SaaS admin dashboard": ("our customers cannot see their account usage numbers as they change",
                             "an admin panel with charts that refresh live for every customer account"),
    "Shopify-to-ERP sync": ("stock levels in our web shop and our warehouse system never match",
                            "keep inventory and orders in sync between the e-commerce store and back-office software"),
    "Learning platform": ("we want to sell our courses online with videos and quizzes",
                          "a learning management website where students watch lessons and take tests"),
    "Real-estate listings site": ("buyers cannot search our homes for sale on a map",
                                  "a property website with search by distance from a location"),
    "Sales performance dashboard": ("regional managers wait a week for sales numbers in spreadsheets",
                                    "an interactive BI report per region that managers can filter themselves"),
    "Marketing attribution analysis": ("we do not know which ads actually bring us customers",
                                       "measure how much each marketing channel contributes to conversions"),
    "dbt warehouse rebuild": ("our warehouse tables are a mess and the numbers in reports never match",
                              "model, test and document our analytics warehouse with daily scheduled runs"),
    "Pricing A/B test": ("we want to try a new price without guessing the result",
                         "design and analyse a controlled experiment comparing two price points"),
    "Inventory Excel automation": ("closing the monthly inventory spreadsheet takes days of copy-paste",
                                   "automate our stock workbook so the month-end numbers fill themselves"),
    "Customer segmentation": ("we send the same email to every customer and results are poor",
                              "group customers by how recently, often and how much they buy, for targeted campaigns"),
}
OPEN = ["We are a {ind} company.", "Small {ind} business here.", "Our {ind} startup is growing fast.", "Hi! We work in {ind}."]
INDUSTRIES = ["fintech", "healthcare", "e-commerce", "education", "logistics", "marketing", "SaaS", "real estate"]
SCAM = ["This is an unpaid test task; if we like it we hire you.", "Please contact me on WhatsApp to discuss, we pay outside the platform."]


def load(pid):
    base = ROOT / pid
    cases = []
    for f in sorted((base / "case_studies").glob("*.md")):
        meta = {}
        for line in f.read_text(encoding="utf-8").split("---")[1].strip().splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = json.loads(v.strip())
        cases.append(meta)
    repos = [f"{pid}-repo-{d.name}" for d in sorted((base / "repos").iterdir()) if d.is_dir()]
    reviews = json.loads((base / "reviews.json").read_text(encoding="utf-8"))
    profile = json.loads((base / "profile.json").read_text(encoding="utf-8"))
    return cases, repos, reviews, profile


def gold_for(project, cases, repos, reviews):
    g = {c["id"]: 2 for c in cases if c["project"] == project}
    slug = project.lower().replace(" ", "-").replace("/", "-")
    g.update({r: 1 for r in repos if r.endswith(slug)})
    g.update({r["id"]: 1 for r in reviews if r["project"] == project})
    return g


def main():
    personas = sorted(p.name for p in ROOT.iterdir() if p.is_dir())
    jobs, n = [], 0
    data = {pid: load(pid) for pid in personas}
    for pid in personas:
        cases, repos, reviews, profile = data[pid]
        projects = list(dict.fromkeys(c["project"] for c in cases))
        skills_of = {c["project"]: c["skills"] for c in cases}
        rate = profile["hourly_rate"]
        band = [round(rate * 0.8), round(rate * 1.4)]

        def add(style, title, desc, skills, gold, bid, scam=False):
            nonlocal n
            n += 1
            jobs.append({"job_id": f"dev-{n:04d}", "persona": pid, "style": style, "title": title, "description": desc,
                         "skills": skills, "budget_type": "hourly", "budget_min": band[0], "budget_max": band[1] + 10,
                         "gold_evidence": gold, "label": "bid" if bid else "skip", "scam": scam,
                         "fair_price_band": band if bid else None, "source": "synthetic"})

        for proj in projects:
            pain, syn = CLIENT[proj]
            other = random.choice([p for p in projects if p != proj])
            for v in range(2):
                ind = random.choice(INDUSTRIES)
                op = random.choice(OPEN).format(ind=ind)
                sk = skills_of[proj]
                add("explicit", f"Build a {proj.lower()}" + (" for our team" if v else ""),
                    f"{op} We need a {proj.lower()} built with {', '.join(sk)}. Please share similar work.", sk,
                    gold_for(proj, cases, repos, reviews), True)
                add("vague", random.choice(["Need help with a business problem", "Looking for an expert", "Project help wanted"]),
                    f"{op} Problem: {pain}. We want this fixed and are open to your suggested approach.", [],
                    gold_for(proj, cases, repos, reviews), True)
                add("synonym", syn.split(" so ")[0].capitalize()[:70],
                    f"{op} We want {syn}. Timeline is flexible for the right person.", [],
                    gold_for(proj, cases, repos, reviews), True)
                g = {**gold_for(proj, cases, repos, reviews), **gold_for(other, cases, repos, reviews)}
                add("multi", "Two connected projects",
                    f"{op} First, {pain}. Second, we also want {CLIENT[other][1]}. Must also write documentation.",
                    sk[:1], g, True)
        # off-niche: projects from OTHER personas -> no evidence, should skip
        foreign = [p for o in personas if o != pid for p in dict.fromkeys(c["project"] for c in data[o][0])]
        for proj in random.sample(foreign, 8):
            pain, syn = CLIENT[proj]
            add("off_niche", f"Need help: {proj.lower()}", f"{random.choice(OPEN).format(ind=random.choice(INDUSTRIES))} "
                f"Problem: {pain}. We want {syn}.", [], {}, False)
        # scams: in-niche text + scam signals
        for proj in random.sample(projects, 4):
            add("scam", f"Quick {proj.lower()} job", f"{CLIENT[proj][0].capitalize()}. {random.choice(SCAM)}",
                skills_of[proj][:2], gold_for(proj, cases, repos, reviews), False, scam=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"{len(jobs)} dev jobs -> {OUT}")
    print(dict(Counter((j['persona'], j['style']) for j in jobs)))


if __name__ == "__main__":
    main()
