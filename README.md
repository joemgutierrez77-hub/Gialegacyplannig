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
```

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
