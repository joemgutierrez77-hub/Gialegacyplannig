# GIA Legacy Planning — Output Maximization Playbook

*A permanent, plain-English record of what has been built, how to squeeze the most
value out of it, and the small set of upgrades worth making. Written to be read once
and referred back to — not rebuilt.*

---

## 1. What you actually have (the honest inventory)

Over the build so far you have shipped **two things that work together**:

**A. The Engine** — a ~3,100-line command-line system (`main.py` + `src/`) that runs the
three parts of the agency:

- **Recruiting** — 11-stage pipeline, candidate scoring, outreach drafts
- **Production** — agent leaderboard, coaching scorecards, funnel gap analysis
- **Profitability** — policy ledger, monthly P&L, chargeback exposure, income projections

It talks to Claude in a *cost-controlled* way (cheap model for simple jobs, expensive
model only for financial strategy), caches prompts, and logs every dollar spent. It reads
from either local files or Airtable. **60 automated tests pass and CI runs on every change.**

**B. The Cockpit** — the last two weeks of work — a no-login, no-Terminal daily portal:

- **FlowHub** (`productivity/index.html`) — tasks, kanban, calendar, notes, Pomodoro, all local
- **Command Center** (`dashboard.html`) — the Jarvis-style Now / Next / Later screen
- **Connectors** — Teamtailor, Calendly, Quility HQ, CSV report imports, and **email → tasks**
- **Live on the web** at `https://joemgutierrez77-hub.github.io/Gialegacyplannig/` — one bookmark, works on Mac and phone

The important part: **the Engine turns raw agency data into decisions, and the Cockpit puts
those decisions in front of you every morning without any technical steps.** That combination
is the asset. Most agencies never get this far.

---

## 2. The core insight

You do not have a *building* problem anymore. You have a **feeding-and-rhythm** problem.

The software's output is only as good as (a) the data you pour into it and (b) how consistently
you open it. A system that sees every recruit, every pending app, and every chargeback — and
that you check at 7am every day — will out-produce a much fancier system that sees half the data
and gets opened twice a week.

So "maximizing output" is three levers, in priority order:

1. **Feed it completely** — every recruit, app, and policy flows in (highest payoff, near-zero build)
2. **Run it on a fixed rhythm** — a daily and weekly cadence you never re-decide (pure discipline)
3. **A short list of favorable upgrades** — small code changes with outsized return (section 4)

---

## 3. Lever 1 & 2 — get full value from what already exists (build nothing)

### Feed it completely
- **Every morning the report exists, import it.** `ImportReports.command` (or `flowhub import-all`)
  routes Pending / Issued / Chargeback rows automatically and is safe to re-run.
- **Connect every inbox once** (`ConnectEmail.command`). Carrier requirements, recruit replies, and
  client messages then become tasks on their own. This is the single biggest force-multiplier you are
  not yet fully using — it turns your inbox into a to-do list without you sorting it.
- **Keep the recruit pipeline current.** Teamtailor sync pulls candidates in; the value shows up only
  if stages get advanced as people move.

### Run it on a fixed rhythm ("set in stone" — section 6 is the printable version)
- **Daily (5 min, 7am):** open the bookmark → clear Top-3 → work the carrier/recruit/client follow-ups
- **Weekly (20 min, Monday):** import the fresh production report, glance at the leaderboard, pick the
  one agent who needs a coaching scorecard
- **Monthly (30 min):** run the P&L and the chargeback exposure report; run one 6-month projection

If you do only section 3, output goes up materially with **zero new software.**

---

## 4. Lever 3 — the favorable upgrades, ranked by payoff vs. effort

These are the changes actually worth making. Ranked so you can stop at any line and still have
captured the biggest wins.

| # | Upgrade | Why it helps | Effort | Payoff |
|---|---------|--------------|--------|--------|
| 1 | **Upgrade the Claude model IDs** | Config still points at older models (`sonnet-4-6`, `opus-4-7`). The current generation (Opus 4.8, Sonnet 5, Haiku 4.5) is smarter *and* cheaper per unit of quality. One-file change in `config/settings.py`. | Tiny | High |
| 2 | **Move the daily sync to the cloud** | Today the 7am sync needs your Mac awake. A scheduled GitHub Action can refresh the dashboard on its own, so the portal is always current even from your phone. | Small | High |
| 3 | **One "morning brief" command** | A single Claude call that reads the day's state and writes a 5-bullet "here's what matters today" summary at the top of the Command Center. Turns data into a decision. | Small | High |
| 4 | **Weekly digest email to yourself** | Reuse the email connector in reverse: every Monday, email yourself the leaderboard + exposure so the review happens even on a busy week. | Small | Medium |
| 5 | **Backup/export button in FlowHub** | Data lives in one browser. A one-click export (and the existing restore) protects against a lost laptop or cleared browser. Partly done — finish and surface it. | Small | Medium |
| 6 | **Persistency + chargeback early-warning** | Flag any agent trending below the 85% persistency floor *before* the chargebacks land, as a red tile on the dashboard. Protects the margin directly. | Medium | High |

**Recommended stopping point: do #1 and #2 now.** They are the "set it and forget it" wins — after
those two, the system keeps itself current and runs on the best models with no ongoing effort.

---

## 5. What NOT to do (protect the asset)

- **Don't add more modules.** The surface area is already right for a one-person-plus-team agency.
  More features = more to maintain, not more production.
- **Don't move data into a new tool.** Airtable + local + the browser app already cover it. Switching
  platforms burns weeks and adds risk.
- **Don't put real client names or credentials in any chat or commit.** The security model (gitignored
  `.env`, local-only data, app passwords, 2-step verification) is correct — keep it. Recent commit #23
  already scrubbed real client data from public files; hold that line.

---

## 6. The operating rhythm — set in stone

> Print this. It is the whole system in six lines. If nothing else survives, this does.

```
DAILY  (7:00am, 5 min)   Open bookmark → clear Top-3 → work carrier/recruit/client follow-ups
WEEKLY (Mon, 20 min)     Import production report → check leaderboard → 1 coaching scorecard
MONTHLY (1st, 30 min)    Run P&L → run chargeback exposure → run one 6-month projection
ALWAYS                   Every report that lands gets imported the same day
NEVER                    Paste a password or real client data into any chat
UPGRADE ONCE             Do items #1 and #2 in section 4, then let it run
```

---

*This document is versioned in the repository, so it is permanent and cannot be lost. Update it
only when the operating rhythm itself changes — the point is that the rhythm rarely should.*
