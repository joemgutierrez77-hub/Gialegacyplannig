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


def _connect_email():
    from src.modules.email_connector import (load_email_accounts, save_email_account,
                                             detect_imap_host)
    accts = load_email_accounts()
    print("\n--- Connect an email account ---")
    print(f"Currently connected: {len(accts)} account(s)")
    print("\nYou need an APP PASSWORD, not your normal email password:")
    print("  • Gmail / Google Workspace: myaccount.google.com → Security → 2-Step Verification → App passwords")
    print("  • Outlook / Hotmail / Microsoft 365: account.microsoft.com → Security → Advanced → App passwords")
    address = input("\nEmail address: ").strip()
    if not address or "@" not in address:
        print("Nothing saved — a valid email address is required.")
        return
    print("Looking up your mail host…")
    host = detect_imap_host(address)
    if host:
        print(f"Detected mail host: {host}")
        override = input("Press Return to accept, or type a different IMAP server: ").strip()
        host = override or host
    else:
        print("Couldn't auto-detect your mail host.")
        print("  • If your email is on Microsoft 365, enter: outlook.office365.com")
        print("  • If it's on Google Workspace, enter:       imap.gmail.com")
        host = input("IMAP server: ").strip()
    if not host:
        print("Nothing saved — an IMAP server is required.")
        return
    provider = "gmail" if "gmail" in host else "outlook" if "office365" in host else "custom"
    password = input("App password (stored only on this Mac): ").strip()
    if not password:
        print("Nothing saved — the app password is required.")
        return
    idx = save_email_account(provider, address, password, host=host)
    print(f"\n✅ Saved account #{idx} ({address} via {host}).")
    print("Add more by running this again, or run `flowhub sync` to scan now.")


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
        from src.modules.email_connector import load_email_accounts
        env = load_env()
        accts = load_email_accounts()
        print("\n--- Connect external tools to FlowHub ---")
        print(f"  Teamtailor:  {'✅ connected' if env.get('TEAMTAILOR_API_KEY') else '— not connected'}")
        print(f"  Calendly:    {'✅ connected' if env.get('CALENDLY_API_TOKEN') else '— not connected'}")
        print(f"  GoHighLevel: {'✅ connected' if env.get('GHL_API_KEY') else '— not connected'}")
        print(f"  Email:       {'✅ ' + str(len(accts)) + ' account(s)' if accts else '— not connected'}")
        print("\nWhich do you want to set up?")
        print("  1) Teamtailor   (recruits sync into your pipeline)")
        print("  2) Calendly     (meetings appear on your FlowHub calendar)")
        print("  3) Email        (carrier/recruit/client emails become tasks + a daily digest)")
        print("  4) GoHighLevel  (appointment-funnel bookings appear on your calendar)")
        choice = input("Enter 1, 2, 3 or 4: ").strip()
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
        elif choice == "3":
            _connect_email()
        elif choice == "4":
            print("\nGet your key: GoHighLevel → Settings → Business Profile → API Key,")
            print("or (newer accounts) Settings → Private Integrations → create token (pit-…)")
            print("with calendar read scopes.")
            key = input("Paste your GoHighLevel API key: ").strip()
            if key:
                save_env_key("GHL_API_KEY", key)
                if key.startswith("pit-"):
                    loc = input("Private tokens also need your Location ID "
                                "(Settings → Business Profile): ").strip()
                    if loc:
                        save_env_key("GHL_LOCATION_ID", loc)
                print("Saved. Run `python main.py flowhub sync` to pull appointments now.")
        else:
            print("Nothing changed.")

    elif sub == "connect-email":
        _connect_email()

    elif sub in ("import-all", "import-policies", "import-pending", "import-chargebacks"):
        from src.modules.connectors import (import_policies_csv, import_pending_csv,
                                            import_chargebacks_csv, import_all_auto)
        if not args.file:
            print(f"Usage: python main.py flowhub {sub} --file <report.csv>")
            return
        try:
            if sub == "import-all":
                res = import_all_auto(args.file, commission_pct=args.commission)
                if res.get("type") == "production":
                    print("\n--- Agent Production Import ---")
                    print(f"  Month {res['month']} · agents added {res['added']}, "
                          f"updated {res['updated']}")
                    for a in res["agents"]:
                        print(f"    - {a['name']:<26} {a['apps']} app(s)  ${a['apv']:,.2f}")
                    if res.get("unmapped"):
                        print(f"  Ignored columns: {', '.join(res['unmapped'][:8])}")
                    print("Run `python main.py flowhub sync` to refresh FlowHub.")
                    return
                print("\n--- Combined Report Import ---")
                for bucket in ("pending", "issued", "chargebacks"):
                    counts = ", ".join(f"{k} {v}" for k, v in res[bucket].items())
                    print(f"  {bucket.capitalize():<12} {counts}")
                if res.get("unmapped"):
                    print(f"  Ignored columns: {', '.join(res['unmapped'][:8])}")
                print("Run `python main.py flowhub sync` to refresh FlowHub.")
                return
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
    fh.add_argument("subcommand", choices=["sync", "connect", "connect-email", "import-all",
                                           "import-policies", "import-pending", "import-chargebacks"])
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
