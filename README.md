# GIA Legacy Planning — Agency Management System

Agency systems, scripts, and automation for running and scaling a life insurance agency.
Covers **Recruiting**, **Production**, and **Profitability** — structured around your business model.

---

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Architecture

```
config/
  settings.py          ← ALL tunable values: models, costs, targets, thresholds

src/
  claude_client.py     ← Single API entry point (caching, logging, model routing)
  prompts/
    recruiting.txt     ← Cached system prompt for recruiting module
    production.txt     ← Cached system prompt for production/coaching module
    profitability.txt  ← Cached system prompt for financial analysis module
  modules/
    recruiting.py      ← Pipeline management + AI scoring/outreach
    production.py      ← Agent stats tracking + AI coaching reports
    profitability.py   ← Policy ledger + P&L + chargeback exposure

data/
  agents/roster.json       ← Agent records
  recruits/pipeline.json   ← Recruit pipeline
  policies/ledger.json     ← Policy ledger
  api_usage.jsonl          ← Every API call logged (tokens + estimated cost)

main.py                    ← CLI entry point
api.py                     ← Mobile API layer (FastAPI) over the same modules
```

---

## Mobile API (phone app back-end)

`api.py` exposes the recruiting / production / profitability modules as a
REST API so a phone app — native, or a no-code builder like **Glide** or
**Softr** — can run the agency from the field.

### Get a permanent link (no terminal) — deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/joemgutierrez77-hub/Gialegacyplannig)

1. Click the button (or go to **dashboard.render.com → New → Blueprint** and
   pick this repo). Render reads `render.yaml` and builds everything.
2. In ~2 minutes you get a permanent URL like
   `https://gia-legacy-planning.onrender.com` — open it on your phone and
   bookmark it / add to your home screen. That's your app.
3. (Optional) In the Render dashboard add `ANTHROPIC_API_KEY` to turn on the AI
   reports, and `AIRTABLE_API_KEY` + `AIRTABLE_BASE_ID` for persistent storage.

> **Note on data:** Render's free tier has an ephemeral disk — local JSON data
> resets when the service restarts. For a permanent record, set the Airtable
> keys (the system already reads/writes Airtable when they're present).

### Run it locally instead

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # optional — only the AI endpoints need it
uvicorn api:app --reload
```

Then open one of these in any browser (including your phone's):

- **http://localhost:8000/** — the mobile **home screen**: live pipeline, this
  month's production vs. targets, override income, and a quick "add recruit" form.
- **http://localhost:8000/docs** — interactive API docs for every endpoint.

To open it from your phone, run the server on a computer and visit
`http://<that-computer's-LAN-IP>:8000/` on the same Wi-Fi (start it with
`uvicorn api:app --host 0.0.0.0` so the phone can reach it).

AI endpoints return a clean `503` (not a crash) if `ANTHROPIC_API_KEY` is unset,
so the home screen and all data endpoints work with no key at all.

| Endpoint | Method | What it does | Claude? |
|---|---|---|---|
| `/dashboard` | GET | Home-screen snapshot: pipeline, team production vs. targets, override income | No (instant/free) |
| `/recruiting/pipeline` | GET | Stage counts | No |
| `/recruiting/recruits` | GET / POST | List / add a recruit | No |
| `/recruiting/recruits/{id}/advance` | POST | Advance a stage (fires the onboarding email) | No |
| `/recruiting/report` | GET | AI pipeline health report | Yes |
| `/recruiting/score` | POST | AI candidate scoring | Yes |
| `/recruiting/outreach` | POST | AI-drafted first-contact message | Yes |
| `/production/agents` | GET / POST | List / add an agent | No |
| `/production/agents/{id}/stats` | POST | Log a month of production | No |
| `/production/leaderboard` | GET | AI team leaderboard | Yes |
| `/production/agents/{id}/scorecard` | GET | AI coaching scorecard | Yes |
| `/production/agents/{id}/gaps` | GET | AI funnel gap analysis | Yes |
| `/profitability/policies` | GET / POST | List / record a policy | No |
| `/profitability/policies/{num}/lapse` | POST | Record a lapse + chargeback | No |
| `/profitability/pnl?month=YYYY-MM` | GET | AI monthly P&L | Yes |
| `/profitability/chargebacks` | GET | AI chargeback exposure | Yes |
| `/profitability/projection?months=6` | GET | AI override income projection | Yes |
| `/usage?since=YYYY-MM-DD` | GET | API spend by module | No |

Read/list endpoints never call Claude, so they're instant and cost nothing —
ideal for a mobile home screen. AI endpoints route through the same
cost-controlled `call_claude` path as the CLI.

---

## Cost Control Strategy

| Technique | What it does | Savings |
|---|---|---|
| **Prompt caching** | System prompts cached after first call | ~90% on repeated calls |
| **Model tiering** | Haiku for simple tasks, Sonnet for analysis, Opus for strategy | 5–20x vs. always using Opus |
| **Token budgets** | Per-model `max_tokens` caps in `config/settings.py` | Prevents runaway output |
| **Usage logging** | Every call logged to `data/api_usage.jsonl` | Full cost visibility |

**Model assignments:**
- `recruiting` → Sonnet (candidate scoring, pipeline analysis)
- `production` → Sonnet (coaching reports, gap analysis)
- `profitability` → Opus (P&L, financial projections — complexity warrants it)
- `data_entry / outreach / leaderboard` → Haiku (simple, high-frequency)

---

## Features

- **Onboarding Phase Tracking**: Detailed 11-stage recruiting pipeline with automatic email alerts on phase changes
- **AI-Powered Analysis**: Claude integration for candidate scoring, coaching reports, and financial projections
- **Cost-Optimized**: Smart model routing, prompt caching, and usage tracking to minimize API costs
- **Dual Data Sources**: Local JSON files or Airtable integration for enterprise deployments
- **Comprehensive CLI**: Full command-line interface for all agency operations

```bash
# Recruiting
python main.py recruiting pipeline                          # show stage counts
python main.py recruiting report                            # AI pipeline health report
python main.py recruiting add -n "Jane Smith" -p "555-0001" -s "referral" -e "jane@example.com"
python main.py recruiting advance --id 1 --stage watched_info
python main.py recruiting score --notes "10 years sales, strong network..."
python main.py recruiting outreach -n "Mike" -s "Facebook ad" -c "expressed interest"

# Production
python main.py production leaderboard                       # ranked team view
python main.py production scorecard --id 1 --months 3      # agent coaching report
python main.py production gaps --id 1                       # funnel gap analysis
python main.py production add-agent -n "Tom Jones" --start-date 2026-01-15 --state TX

# Profitability
python main.py profitability pnl --month 2026-04            # monthly P&L
python main.py profitability chargebacks                    # exposure report
python main.py profitability projection --months 6          # income forecast

# Cost audit
python main.py usage                                        # all-time API spend by module
python main.py usage --since 2026-04-01                     # since a specific date
```

---

## Business Targets (edit in `config/settings.py`)

| Metric | Target |
|---|---|
| Apps submitted / agent / month | 8 |
| Issued policies / agent / month | 6 |
| APV / agent / month | $10,000 |
| 13-month persistency | ≥ 85% |
| Recruits contacted / month | 20 |
| Recruits interviewed / month | 8 |
| Contracts issued / month | 3 |
| Agency profit margin | ≥ 20% |
| Chargeback reserve | 10% of gross commission |
