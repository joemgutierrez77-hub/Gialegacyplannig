"""
Airtable adapter — drop-in replacement for the local JSON data layer.

Activated automatically when AIRTABLE_API_KEY + AIRTABLE_BASE_ID are set.
Falls back to local JSON if those env vars are absent so development and
CI work without credentials.

All reads/writes go through the four public functions that mirror the
local-storage interface used by the three business modules.
"""

from datetime import datetime
from typing import Optional

from config.settings import (
    AGENCY,
    AIRTABLE_API_KEY,
    AIRTABLE_BASE_ID,
    AIRTABLE_FIELDS as F,
    AIRTABLE_TABLES as T,
)

# ---------------------------------------------------------------------------
# Internal Airtable HTTP helpers (no third-party lib needed)
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.airtable.com/v0"


def _headers() -> dict:
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}


def _get_all_records(table_name: str, filter_formula: str = "") -> list:
    """Fetch every record from a table, handling Airtable's 100-record pagination."""
    import requests  # lazy import — only needed when Airtable is active

    url    = f"{_BASE_URL}/{AIRTABLE_BASE_ID}/{requests.utils.quote(table_name)}"
    params = {}
    if filter_formula:
        params["filterByFormula"] = filter_formula

    records = []
    offset  = None

    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        body    = resp.json()
        records.extend(body.get("records", []))
        offset  = body.get("offset")
        if not offset:
            break

    return records


def _create_record(table_name: str, fields: dict) -> dict:
    import requests
    url  = f"{_BASE_URL}/{AIRTABLE_BASE_ID}/{requests.utils.quote(table_name)}"
    resp = requests.post(url, headers=_headers(), json={"fields": fields}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _update_record(table_name: str, record_id: str, fields: dict) -> dict:
    import requests
    url  = f"{_BASE_URL}/{AIRTABLE_BASE_ID}/{requests.utils.quote(table_name)}/{record_id}"
    resp = requests.patch(url, headers=_headers(), json={"fields": fields}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _list_fields(table_name: str) -> list:
    """Return all field names present in the first record of a table."""
    records = _get_all_records(table_name)
    if not records:
        return []
    return sorted(records[0].get("fields", {}).keys())


# ---------------------------------------------------------------------------
# Public API — mirrors the local JSON interface used by business modules
# ---------------------------------------------------------------------------

# ---- Policies / Issued --------------------------------------------------

def get_issued_policies(status_filter: Optional[str] = None) -> list:
    """
    Return issued policies from Airtable, optionally filtered by status.
    Each record is normalised to the same dict shape as the local ledger.
    """
    formula = ""
    if status_filter:
        formula = f"{{%s}}='{status_filter}'" % F["policy_status"]

    raw = _get_all_records(T["issued"], filter_formula=formula)
    return [_normalise_policy(r) for r in raw]


def _normalise_policy(record: dict) -> dict:
    flds = record.get("fields", {})
    return {
        "airtable_id":          record["id"],
        "agent_id":             flds.get(F["agent_id"], ""),
        "agent_name":           flds.get(F["agent_name"], ""),
        "policy_number":        flds.get(F["policy_number"], ""),
        "carrier":              flds.get(F["carrier"], ""),
        "issue_date":           flds.get(F["issue_date"], ""),
        "annual_premium":       float(flds.get(F["annual_premium"], 0) or 0),
        "agent_commission_pct": float(flds.get(F["commission_pct"], 0) or 0),
        "gross_commission":     float(flds.get(F["gross_commission"], 0) or 0),
        "agency_override":      float(flds.get(F["agency_override"], 0) or 0),
        "chargeback_reserve":   float(flds.get(F["chargeback_reserve"], 0) or 0),
        "net_to_agent":         float(flds.get(F["net_to_agent"], 0) or 0),
        "status":               flds.get(F["policy_status"], "active").lower(),
        "persistency":          flds.get(F["persistency"], None),
    }


def write_issued_policy(
    agent_id:             str,
    agent_name:           str,
    policy_number:        str,
    carrier:              str,
    issue_date:           str,
    annual_premium:       float,
    agent_commission_pct: float,
) -> dict:
    """Create an issued-policy record in Airtable with financials auto-calculated."""
    gross    = round(annual_premium * agent_commission_pct, 2)
    override = round(annual_premium * AGENCY["override_rate"], 2)
    reserve  = round(gross * AGENCY["chargeback_reserve_pct"], 2)
    net      = round(gross - reserve, 2)

    fields = {
        F["agent_id"]:          agent_id,
        F["agent_name"]:        agent_name,
        F["policy_number"]:     policy_number,
        F["carrier"]:           carrier,
        F["issue_date"]:        issue_date,
        F["annual_premium"]:    annual_premium,
        F["commission_pct"]:    agent_commission_pct,
        F["gross_commission"]:  gross,
        F["agency_override"]:   override,
        F["chargeback_reserve"]:reserve,
        F["net_to_agent"]:      net,
        F["policy_status"]:     "Active",
    }
    return _create_record(T["issued"], fields)


def mark_policy_lapsed(policy_number: str, chargeback_amount: float) -> dict:
    """Find the issued policy by policy number and update it to Lapsed."""
    formula  = f"{{%s}}='{policy_number}'" % F["policy_number"]
    records  = _get_all_records(T["issued"], filter_formula=formula)
    if not records:
        raise ValueError(f"Policy '{policy_number}' not found in Airtable.")

    record   = records[0]
    record_id = record["id"]
    current_net = float(record["fields"].get(F["net_to_agent"], 0) or 0)

    return _update_record(T["issued"], record_id, {
        F["policy_status"]:     "Lapsed",
        F["chargeback_amount"]: chargeback_amount,
        F["net_to_agent"]:      round(current_net - chargeback_amount, 2),
    })


# ---- Pending applications -----------------------------------------------

def get_pending_apps() -> list:
    """Return all pending applications as normalised dicts."""
    raw = _get_all_records(T["pending"])
    return [_normalise_pending(r) for r in raw]


def _normalise_pending(record: dict) -> dict:
    flds = record.get("fields", {})
    return {
        "airtable_id":    record["id"],
        "agent_name":     flds.get(F["agent_name"], ""),
        "applicant_name": flds.get(F["applicant_name"], ""),
        "carrier":        flds.get(F["carrier"], ""),
        "annual_premium": float(flds.get(F["annual_premium"], 0) or 0),
        "submit_date":    flds.get(F["submit_date"], ""),
        "status":         flds.get(F["app_status"], "Pending"),
        "policy_number":  flds.get(F["policy_number"], ""),
    }


def write_pending_app(
    agent_name:     str,
    applicant_name: str,
    carrier:        str,
    annual_premium: float,
    submit_date:    Optional[str] = None,
) -> dict:
    """Add a new submitted application to the Pending table."""
    fields = {
        F["agent_name"]:     agent_name,
        F["applicant_name"]: applicant_name,
        F["carrier"]:        carrier,
        F["annual_premium"]: annual_premium,
        F["submit_date"]:    submit_date or datetime.today().strftime("%Y-%m-%d"),
        F["app_status"]:     "Pending",
    }
    return _create_record(T["pending"], fields)


def promote_to_issued(
    pending_record_id:    str,
    policy_number:        str,
    issue_date:           str,
    agent_commission_pct: float,
) -> dict:
    """
    Mark a pending app as Approved and create the matching Issued record.
    Returns the new Issued record.
    """
    # 1. Update the pending record status
    _update_record(T["pending"], pending_record_id, {
        F["app_status"]:    "Approved",
        F["policy_number"]: policy_number,
    })

    # 2. Pull the pending record's data to copy into Issued
    pending_records = _get_all_records(
        T["pending"],
        filter_formula=f"RECORD_ID()='{pending_record_id}'"
    )
    if not pending_records:
        raise ValueError(f"Pending record {pending_record_id} not found.")

    flds = pending_records[0]["fields"]
    return write_issued_policy(
        agent_id             = flds.get(F["agent_id"], ""),
        agent_name           = flds.get(F["agent_name"], ""),
        policy_number        = policy_number,
        carrier              = flds.get(F["carrier"], ""),
        issue_date           = issue_date,
        annual_premium       = float(flds.get(F["annual_premium"], 0) or 0),
        agent_commission_pct = agent_commission_pct,
    )


# ---- Recruits -----------------------------------------------------------

def get_recruits(stage: Optional[str] = None) -> list:
    formula = f"{{%s}}='{stage}'" % F["recruit_stage"] if stage else ""
    raw = _get_all_records(T["recruits"], filter_formula=formula)
    return [_normalise_recruit(r) for r in raw]


def _normalise_recruit(record: dict) -> dict:
    flds = record.get("fields", {})
    return {
        "airtable_id": record["id"],
        "name":        flds.get(F["recruit_name"], ""),
        "phone":       flds.get(F["recruit_phone"], ""),
        "source":      flds.get(F["recruit_source"], ""),
        "stage":       flds.get(F["recruit_stage"], "lead"),
        "notes":       flds.get(F["recruit_notes"], ""),
        "added_date":  flds.get(F["recruit_added_date"], ""),
    }


def write_recruit(name: str, phone: str, source: str, notes: str = "") -> dict:
    fields = {
        F["recruit_name"]:       name,
        F["recruit_phone"]:      phone,
        F["recruit_source"]:     source,
        F["recruit_stage"]:      "lead",
        F["recruit_notes"]:      notes,
        F["recruit_added_date"]: datetime.today().strftime("%Y-%m-%d"),
    }
    return _create_record(T["recruits"], fields)


def advance_recruit_stage(record_id: str, new_stage: str, notes: str = "") -> dict:
    fields = {F["recruit_stage"]: new_stage}
    if notes:
        fields[F["recruit_notes"]] = notes
    return _update_record(T["recruits"], record_id, fields)


# ---- Inspection ---------------------------------------------------------

def inspect_tables() -> dict:
    """Return the field names found in each table — useful for verifying mapping."""
    result = {}
    for key, table_name in T.items():
        try:
            result[table_name] = _list_fields(table_name)
        except Exception as exc:
            result[table_name] = [f"ERROR: {exc}"]
    return result
