#!/usr/bin/env python3
"""
GIA Legacy Planning — Agency Management CLI

Usage:
  python main.py recruiting pipeline
  python main.py recruiting add "John Doe" "555-1234" "referral"
  python main.py recruiting score <recruit_id>
  python main.py production leaderboard
  python main.py production scorecard <agent_id>
  python main.py production gaps <agent_id>
  python main.py profitability pnl 2026-04
  python main.py profitability chargebacks
  python main.py profitability projection
  python main.py usage [--since YYYY-MM-DD]
"""

import argparse

from src.claude_client import cost_summary
from src.modules.recruiting    import (add_recruit, advance_stage,
                                        pipeline_summary, score_candidate,
                                        draft_outreach, pipeline_health_report)
from src.modules.production    import (add_agent, agent_scorecard, team_leaderboard,
                                        activity_gap_analysis)
from src.modules.profitability import (monthly_pnl_report,
                                        chargeback_exposure_report,
                                        override_income_projection)


def cmd_recruiting(args):
    sub = args.subcommand
    if sub == "pipeline":
        summary = pipeline_summary()
        print("\n--- Recruiting Pipeline ---")
        for stage, count in summary.items():
            print(f"  {stage:<15} {count}")

    elif sub == "report":
        print(pipeline_health_report())

    elif sub == "add":
        r = add_recruit(args.name, args.phone, args.source, args.notes or "")
        print(f"Added recruit #{r['id']}: {r['name']}")

    elif sub == "advance":
        r = advance_stage(args.id, args.stage, args.notes or "")
        print(f"Recruit #{r['id']} advanced to '{r['stage']}'")

    elif sub == "score":
        notes = args.notes or input("Paste candidate interview notes:\n> ")
        print(score_candidate(notes))

    elif sub == "outreach":
        msg = draft_outreach(args.name, args.source, args.context or "")
        print(f"\nSuggested message:\n{msg}")

    else:
        print(f"Unknown recruiting subcommand: {sub}")


def cmd_production(args):
    sub = args.subcommand
    if sub == "leaderboard":
        print(team_leaderboard())

    elif sub == "scorecard":
        print(agent_scorecard(args.id, months=args.months or 3))

    elif sub == "gaps":
        print(activity_gap_analysis(args.id))

    elif sub == "add-agent":
        a = add_agent(args.name, args.start_date, args.state)
        print(f"Added agent #{a['id']}: {a['name']}")

    else:
        print(f"Unknown production subcommand: {sub}")


def cmd_profitability(args):
    sub = args.subcommand
    if sub == "pnl":
        month = args.month or input("Enter month (YYYY-MM): ").strip()
        print(monthly_pnl_report(month))

    elif sub == "chargebacks":
        print(chargeback_exposure_report())

    elif sub == "projection":
        months = args.months or 6
        print(override_income_projection(months))

    else:
        print(f"Unknown profitability subcommand: {sub}")


def cmd_usage(args):
    since = getattr(args, "since", None)
    summary = cost_summary(since_date=since)
    if not summary:
        print("No API usage recorded yet.")
        return
    print(f"\n--- API Cost Summary {'since ' + since if since else '(all time)'} ---")
    total = 0.0
    for module, cost in summary.items():
        print(f"  {module:<20} ${cost:.4f}")
        total += cost
    print(f"  {'TOTAL':<20} ${total:.4f}")


def main():
    parser = argparse.ArgumentParser(
        description="GIA Legacy Planning — Agency Management CLI"
    )
    sub = parser.add_subparsers(dest="command")

    # ---- recruiting ----
    rec = sub.add_parser("recruiting")
    rec.add_argument("subcommand", choices=["pipeline","report","add","advance","score","outreach"])
    rec.add_argument("--name",    "-n")
    rec.add_argument("--phone",   "-p")
    rec.add_argument("--source",  "-s")
    rec.add_argument("--notes",   "-o")
    rec.add_argument("--context", "-c")
    rec.add_argument("--id",      type=int)
    rec.add_argument("--stage")

    # ---- production ----
    prod = sub.add_parser("production")
    prod.add_argument("subcommand", choices=["leaderboard","scorecard","gaps","add-agent"])
    prod.add_argument("--id",         type=int)
    prod.add_argument("--months",     type=int)
    prod.add_argument("--name",       "-n")
    prod.add_argument("--start-date", "-d")
    prod.add_argument("--state")

    # ---- profitability ----
    prof = sub.add_parser("profitability")
    prof.add_argument("subcommand", choices=["pnl","chargebacks","projection"])
    prof.add_argument("--month",  "-m")
    prof.add_argument("--months", type=int)

    # ---- usage ----
    usg = sub.add_parser("usage")
    usg.add_argument("--since", help="YYYY-MM-DD")

    args = parser.parse_args()

    if args.command == "recruiting":
        cmd_recruiting(args)
    elif args.command == "production":
        cmd_production(args)
    elif args.command == "profitability":
        cmd_profitability(args)
    elif args.command == "usage":
        cmd_usage(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
