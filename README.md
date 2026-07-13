# GIA Legacy Planning — Agency Management System

Agency systems, scripts, and automation for running and scaling a life insurance agency.
Covers **Recruiting**, **Production**, and **Profitability** — structured around your business model.

---

## Security & your credentials

This system is built so your secrets never leave your machine:

- **All credentials** (email app passwords, Teamtailor/Calendly keys) live only in a local
  `.env` file. It is **gitignored** — never committed, never uploaded.
- Your imported data (`data/`) and the generated `productivity/business-data.js` are also
  gitignored and stay on your computer.
- **Never paste a password or API key into a chat** — with Claude/ChatGPT or anyone. Chat
  messages can be stored, so anything typed there should be treated as exposed. Enter
  credentials only into the local prompts (`ConnectEmail.command` / `flowhub connect`),
  which write them to `.env` on your machine.
- Use **app passwords**, not your main account password, for email. App passwords are scoped
  to mail only and can be revoked anytime without changing your real password.
- Turn on **two-step verification** on each email account. Then even a leaked password is
  useless to anyone without the code on your phone — this is the single strongest protection.
- If a credential is ever exposed: revoke/regenerate it in your account's security settings
  (delete the app password, rotate the API key) and it stops working immediately.

---

## FlowHub — Personal Productivity App

A self-contained personal productivity tool lives in [`productivity/index.html`](productivity/index.html).
Open the file in any browser — no install, no server, no dependencies. All data is saved
privately in your browser's local storage.

**Modules (deeply integrated):**

- **Dashboard** — today's tasks, overdue alerts, upcoming events, focus stats, quick capture
- **Tasks** — projects, tags, priorities, due dates, subtasks, recurring tasks
- **Kanban board** — drag-and-drop columns (Backlog / To Do / In Progress / Done) over the same tasks
- **Calendar** — month + week (hourly) views, events with recurrence, task due dates overlaid, drag to reschedule
- **Notes** — markdown editor with live preview, notebooks, tags, full-text search, pinning
- **Pomodoro** — 25/5 with long breaks, link sessions to tasks, chime + browser notifications, stats & streaks
- **Arcade** — classic Snake with high-score tracking for screen breaks
- **Business** — live agency overview + auto-generated daily tasks from your real data (see below)

### Live business data → daily tasks

```bash
python main.py flowhub sync
```

This reads your agency data (local JSON or Airtable, same as the rest of the system)
and writes `productivity/business-data.js` next to the app. On the next page load, FlowHub:

- Shows a **Business** view: pipeline stage counts, agent production vs targets, APV, chargeback exposure
- **Auto-adds daily tasks** from real business state — new-lead outreach, stalled-recruit follow-ups,
  coaching sessions for agents below APV/persistency targets, missing monthly stats, recruiting quota
  pace, and chargeback reviews — each due today, in an "Agency" project
- Never duplicates: every suggestion has a stable key, so re-running the sync only adds what's new

Run the sync each morning (or add it to a scheduled job) so your to-do list is pre-filled
before you start the day. `business-data.js` is gitignored — your business data stays local.

### External connectors — Teamtailor, Calendly, Quility HQ

Pull data from the tools you already use, with a guided setup:

```bash
python main.py flowhub connect                             # paste in API keys (saved to gitignored .env)
python main.py flowhub sync                                # connectors run automatically on every sync
python main.py flowhub import-all         --file report.csv  # ONE report with a Status column (recommended)
python main.py flowhub import-pending     --file apps.csv  # submitted/pending applications
python main.py flowhub import-policies    --file issued.csv  # issued policies
python main.py flowhub import-chargebacks --file cb.csv    # chargebacks (marks policies lapsed)
```

`import-all` auto-detects the report shape. A **per-policy** report (one row per policy, with a
Status column) is routed by each row's Status: Pending/Submitted → pending apps, Issued/Active →
ledger, Lapsed/Chargeback/Cancelled → chargebacks. A **per-agent production summary** (agent name +
APV + app counts per agent, e.g. Quility HQ "Submitted Details") instead updates each agent's
monthly production on the roster — so agent names are kept and submitted business is never
mis-booked as issued, paid policies. Re-importing an updated report is always safe: per-policy rows
are skipped or status-updated, and a re-pulled production summary replaces that agent's month rather
than double-counting.

On macOS, **`ImportReports.command`** (project root) does it all without typing: double-click,
pick the report type, drag the CSV into the window. Pending apps stuck in underwriting 14+ days
automatically become follow-up tasks; chargebacks update the active book and exposure totals.

### Email → tasks + daily digest (Gmail, Outlook/Microsoft 365, Hotmail)

```bash
python main.py flowhub connect-email      # add an account (repeat per inbox)
python main.py flowhub sync               # email is scanned automatically every sync
```

Connect each inbox with just your **email address + app password** (not your normal password —
generate one under your account's 2-step-verification/security settings). The setup auto-detects
your mail host from the address — including **custom domains** (e.g. an agency domain on
Microsoft 365 or Google Workspace) via an MX lookup, with a manual override if needed. FlowHub
then, on every sync, scans the last few days and:

- **Carrier emails** (Mutual of Omaha, AIG, Americo, NLG, F&G, TransAmerica, etc.) → tasks,
  high priority when they mention a requirement/declined/lapse/payment issue
- **Recruit replies** (sender matches your pipeline) → follow-up tasks
- **Client messages** (sender matches an insured/applicant) → respond tasks
- A **📬 Inbox Digest** panel in the Business view summarizing recent mail by category

Everything runs locally via IMAP. Email contents are **never uploaded or committed** — only the
derived tasks and a short digest go into the gitignored `business-data.js`, and credentials live
only in your gitignored `.env`. On macOS, **`ConnectEmail.command`** walks you through setup.
Note: some Microsoft 365 *business* accounts have IMAP app-passwords disabled by an admin; in
that case ask your admin to enable IMAP, or use your personal Gmail/Hotmail.

- **Teamtailor** — candidates flow into the recruiting pipeline as new leads (deduplicated,
  never moved backward once you advance them)
- **Calendly** — upcoming meetings appear on the FlowHub calendar and stay current if rescheduled
- **Quility HQ / carriers** — download any policy report as CSV and import it; flexible column
  matching (Policy #/Agent/Carrier/Premium/Status), deduplicated by policy number

### macOS one-click launch & automatic daily sync

- **`FlowHub.command`** (project root) — double-click to sync business data and open FlowHub
  in your browser in one step. macOS may ask you to right-click → Open the first time.
- **`Dashboard.command`** (project root) — double-click to refresh live data and open the
  G.I.A. command center (`dashboard.html`) — a Jarvis-style Now / Next / Later cockpit.
- **`scripts/setup-daily-sync.command`** — double-click once to schedule the sync to run
  automatically every morning at 7:00 (uses a launchd agent; catches up after sleep,
  logs to `~/Library/Logs/flowhub-sync.log`).
- **`scripts/remove-daily-sync.command`** — removes the schedule.

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
