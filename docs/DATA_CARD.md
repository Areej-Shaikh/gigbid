# Data Card: GigBid / GigSim

GigSim (our mock marketplace) is filled with **real Upwork job data from Kaggle** plus **synthetic records** we generated for things the real data does not contain. Every record has a `source` field: `"real"` or `"synthetic"`.

Build command: `python scripts/prepare_data.py` → writes `data/processed/gigsim_db.json` and `data/processed/price_stats.json`.

---

## 1. Real datasets used

| File in `data/raw/` | Kaggle dataset | Author | License | Rows (raw) | Usable rows | Used for |
|---|---|---|---|---|---|---|
| `upwork-jobs.csv` | [Upwork Job Postings Dataset 2024 (50k)](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | asaniczka | [ODC-By 1.0](https://opendatacommons.org/licenses/by/1-0/) | 53,058 | 44,829 | Jobs: title, description, hourly/fixed budget, date, country; price statistics |
| `Final_Upwork_Dataset.csv` | [Upwork Freelance Jobs (60k)](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | ahmedmyalo | [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) | 63,950 | 46,683 | Jobs + skills (Category_1–9), real Connects cost, experience level, **real client info** (payment verified, amount spent, rating, number of reviews, country) |

**Total usable real jobs: 91,512.** GigSim contains 1,580 jobs (1,500 real + 80 synthetic) and 1,050 clients (750 real + 300 synthetic).

Raw CSVs are **not committed** (size and license). To reproduce: download them from the links above into `data/raw/`, then run the build command.

## 2. Preprocessing

1. Column names are matched automatically (e.g. `title` / `Job Title`, `budget` / `Job_Cost`).
2. Rows without a title or without a usable price (budget or hourly rate > 0) are dropped.
3. Budget type: `hourly` if the job is marked hourly, otherwise `fixed`. Money strings like `"$2,500"` are converted to numbers.
4. Skills: taken from `Category_1–9` when available; otherwise extracted from the title and description using a fixed keyword list.
5. Descriptions are cut to 3,000 characters and titles to 200.
6. **Sampling:** 750 jobs at random from each dataset (1,500 real jobs total), with a fixed random seed (42) so the output is the same every run.
7. **Connects cost:** the real `New_Connects_Num` value when present; otherwise estimated from the budget (4 / 8 / 12 / 16).
8. **Price statistics:** for every skill with at least 5 jobs, the 25th percentile, median and 75th percentile of price, split by hourly and fixed. These are computed on **all** 91,512 usable real jobs, not only the sample, and cover **1,774 skills**.

## 3. Synthetic data (generated, not real)

| What | How many | Why |
|---|---|---|
| Clients for `upwork-jobs.csv` jobs | 300 | That dataset has no client info. About 15% are made "risky" (not verified, $0 spent, no hires). |
| Freelancer account | 1 | Starting Connects balance = 80 |
| Scam jobs | 30 | Test the Risk Assessor: unpaid "test" work, off-platform contact (WhatsApp/Telegram), requests for bank details |
| Prompt-injection jobs | 20 | Copies of real jobs with an injected instruction added to the description (e.g. "IGNORE ALL PREVIOUS INSTRUCTIONS…") |
| Duplicate jobs | 30 | Exact copies of real jobs with a new ID, to test de-duplication in the Scout |
| Freelancer personas (`data/personas/`) | 3 | AI/ML engineer, full-stack developer, data analyst. Kaggle has no portfolios. Built by `scripts/generate_personas.py` (seed 7). |
| Case studies | 18 per persona | Same project written 3 different ways; every 3rd one only *implies* a skill in the text instead of tagging it |
| Repositories | 5 per persona | Vague README + code file whose header shows the real stack (README alone looks irrelevant) |
| Client reviews | 10 per persona | Linked to case studies |
| Past proposals | 150 per persona | Labelled won / replied / ignored by a hidden rule: citing specific evidence and skill fit raise the chance; generic openings lower it |

Synthetic jobs carry a hidden `labels` field (`scam`, `prompt_injection`, `duplicate_of:<id>`). **GigSim hides `labels`, `source` and `dataset` from the API**, so agents cannot see the answers; only evaluation scripts read them.

## 4. Real client records

`Final_Upwork_Dataset.csv` has client columns but **no client ID**, so each job gets its own client record (`rc-XXXXX`) built from that row. This means we cannot see the same client posting several jobs.

## 5. Limitations

- **Old snapshot:** prices and demand reflect when the data was scraped (around 2024), not today.
- **No outcomes:** we don't know who won the job, how many proposals were sent, or whether clients replied. Reply and hire outcomes in GigSim are simulated.
- **Client info is partial:** real only for the Final dataset; synthetic for the other.
- **Missing values:** some jobs have no description, rating or hourly range.
- **Skill extraction by keywords** misses skills that aren't on the list or are only implied.
- **Bias:** both datasets are scraped from search pages for certain keywords and categories (many are tech or data jobs), so they don't represent all of Upwork.
- **Synthetic scams and injections** are simple templates; real scams are more varied.

## 6. Ethics and privacy

- The data is public job posts from Kaggle; no freelancer personal data is used.
- We do not scrape Upwork. All live access (if used) goes through the official Upwork MCP server.
- Raw data, processed data, the hidden test set and any live-mode data are never committed.
