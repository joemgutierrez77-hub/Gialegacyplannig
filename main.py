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
        r = add_recruit(args.name, args.phone, args.source, args.notes or "", args.email or "")
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


def cmd_flowhub(args):
    sub = args.subcommand
    if sub == "sync":
        from src.modules.flowhub import build_snapshot, export_flowhub
        path = export_flowhub()
        snap = build_snapshot()
        print(f"\n--- FlowHub Sync ({snap['source']}) ---")
        print(f"  Recruits in pipeline:   {snap['recruiting']['total']}")
        print(f"  Active agents tracked:  {len(snap['production']['agents'])}")
        print(f"  Active policies:        {snap['profitability']['activePolicies']}")
        print(f"  Suggested daily tasks:  {len(snap['suggestions'])}")
        print(f"\nWrote {path}")
        print("Open productivity/index.html — new business tasks appear automatically.")

    elif sub == "connect":
        from src.modules.connectors import load_env, save_env_key
        env = load_env()
        print("\n--- Connect external tools to FlowHub ---")
        print(f"  Teamtailor: {'✅ connected' if env.get('TEAMTAILOR_API_KEY') else '— not connected'}")
        print(f"  Calendly:   {'✅ connected' if env.get('CALENDLY_API_TOKEN') else '— not connected'}")
        print("\nWhich do you want to set up?")
        print("  1) Teamtailor  (recruits sync into your pipeline)")
        print("  2) Calendly    (meetings appear on your FlowHub calendar)")
        choice = input("Enter 1 or 2: ").strip()
        if choice == "1":
            print("\nGet your key: Teamtailor → Settings → API keys → New API key (read scope).")
            key = input("Paste your Teamtailor API key: ").strip()
            if key:
                save_env_key("TEAMTAILOR_API_KEY", key)
                print("Saved. Run `python main.py flowhub sync` to pull candidates now.")
        elif choice == "2":
            print("\nGet your token: Calendly → Integrations & apps → API & webhooks →")
            print("Personal access tokens → Generate new token.")
            key = input("Paste your Calendly token: ").strip()
            if key:
                save_env_key("CALENDLY_API_TOKEN", key)
                print("Saved. Run `python main.py flowhub sync` to pull meetings now.")
        else:
            print("Nothing changed.")

    elif sub in ("import-policies", "import-pending", "import-chargebacks"):
        from src.modules.connectors import (import_policies_csv, import_pending_csv,
                                            import_chargebacks_csv)
        if not args.file:
            print(f"Usage: python main.py flowhub {sub} --file <report.csv>")
            return
        try:
            if sub == "import-policies":
                res = import_policies_csv(args.file, commission_pct=args.commission)
                label = "Issued Policy Import"
            elif sub == "import-pending":
                res = import_pending_csv(args.file)
                label = "Pending Application Import"
            else:
                res = import_chargebacks_csv(args.file)
                label = "Chargeback Import"
        except (ValueError, FileNotFoundError) as e:
            print(f"Import failed: {e}")
            return
        print(f"\n--- {label} ---")
        for k in ("added", "updated", "skipped"):
            if k in res:
                print(f"  {k.capitalize():<8} {res[k]}")
        if res.get("unmapped"):
            print(f"  Ignored columns: {', '.join(res['unmapped'][:8])}")
        print("Run `python main.py flowhub sync` to refresh FlowHub.")
    else:
        print(f"Unknown flowhub subcommand: {sub}")


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


def cmd_airtable(args):
    from config.settings import USE_AIRTABLE, AIRTABLE_BASE_ID, AIRTABLE_TABLES
    sub = args.subcommand

    if sub == "status":
        print("\n--- Airtable Integration Status ---")
        print(f"  Active:  {USE_AIRTABLE}")
        print(f"  Base ID: {AIRTABLE_BASE_ID}")
        for key, name in AIRTABLE_TABLES.items():
            print(f"  Table [{key}]: '{name}'")

    elif sub == "inspect":
        if not USE_AIRTABLE:
            print("Airtable is not active. Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID first.")
            return
        from src.airtable_adapter import inspect_tables
        print("\n--- Live Airtable Field Names ---")
        for table, fields in inspect_tables().items():
            print(f"\n  [{table}]")
            for f in fields:
                print(f"    • {f}")

    elif sub == "pending":
        if not USE_AIRTABLE:
            print("Airtable is not active.")
            return
        from src.airtable_adapter import get_pending_apps
        apps = get_pending_apps()
        print(f"\n--- Pending Applications ({len(apps)}) ---")
        for a in apps:
            print(f"  {a['submit_date']}  {a['agent_name']:<20} {a['applicant_name']:<20}"
                  f"  {a['carrier']:<15}  ${a['annual_premium']:,.0f}  [{a['status']}]")

    elif sub == "issued":
        if not USE_AIRTABLE:
            print("Airtable is not active.")
            return
        from src.airtable_adapter import get_issued_policies
        policies = get_issued_policies()
        print(f"\n--- Issued Policies ({len(policies)}) ---")
        for p in policies:
            print(f"  {p['issue_date']}  {p['agent_name']:<20} {p['policy_number']:<15}"
                  f"  {p['carrier']:<15}  APV ${p['annual_premium']:,.0f}"
                  f"  Net ${p['net_to_agent']:,.0f}  [{p['status']}]")

    else:
        print(f"Unknown airtable subcommand: {sub}")


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
    rec.add_argument("--email",   "-e")
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

    # ---- airtable ----
    at = sub.add_parser("airtable")
    at.add_argument("subcommand", choices=["status", "inspect", "pending", "issued"])

    # ---- flowhub ----
    fh = sub.add_parser("flowhub")
    fh.add_argument("subcommand", choices=["sync", "connect", "import-policies",
                                           "import-pending", "import-chargebacks"])
    fh.add_argument("--file", "-f", help="CSV report to import")
    fh.add_argument("--commission", type=float, default=0.70,
                    help="Agent commission rate for imported policies (default 0.70)")

    args = parser.parse_args()

    if args.command == "recruiting":
        cmd_recruiting(args)
    elif args.command == "production":
        cmd_production(args)
    elif args.command == "profitability":
        cmd_profitability(args)
    elif args.command == "usage":
        cmd_usage(args)
    elif args.command == "airtable":
        cmd_airtable(args)
    elif args.command == "flowhub":
        cmd_flowhub(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
