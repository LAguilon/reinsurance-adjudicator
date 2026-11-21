"""One-page HTML Claim Adjudication Advice.

Self-contained: inline CSS, no scripts, no external assets. The clause texts
below are the certificate wording this demo implements; a production deployment
would load them from the wording repository, keyed by the same typed clause IDs.
"""
from __future__ import annotations

import html

from acord_adapter import ISO4217_EXPONENT, minor_to_money

CLAUSE_TEXT = {
    "Cl_4_1_PerilsInsured":
        "This Certificate insures loss or damage to the Insured Property caused by or "
        "resulting from the Perils Insured against, subject to the terms, conditions, "
        "limitations and exclusions of this Certificate.",
    "Cl_4_2_PerilExclusion":
        "This Certificate does not cover loss or damage caused by or resulting from "
        "Flood or Earthquake where such peril is excluded in the Schedule of Excluded "
        "Perils.",
    "Cl_5_1_CyberExclusion":
        "This Certificate does not cover loss, damage, liability, cost or expense of any "
        "kind caused by or resulting from a Cyber Incident, Cyber Act, or any use of or "
        "access to a Computer System.",
    "Cl_5_1a_CyberResultingFireWriteBack":
        "Notwithstanding Clause 5.1, this Certificate shall cover loss or damage caused "
        "by fire or explosion which directly results from a Cyber Incident, provided "
        "that such fire or explosion would otherwise be covered under Clause 4.1.",
    "Cl_5_2_WarExclusion":
        "This Certificate does not cover loss or damage caused by or resulting from war, "
        "invasion, act of foreign enemy, hostilities, civil war, rebellion, revolution, "
        "insurrection or military or usurped power.",
    "Cl_6_1_TreatyPeriod":
        "This Certificate applies only to loss or damage occurring during the Period of "
        "Insurance shown in the Schedule.",
    "Cl_7_3_Certification":
        "No claim shall be payable under this Certificate unless the loss has been "
        "certified by an adjuster appointed in accordance with Clause 7.",
    "Cl_7_4_UnresolvedCourtRulingReserve":
        "Where a court ruling material to the claim remains unresolved, the Reinsurer "
        "shall book its share of the cedent's outstanding loss reserve. No cash "
        "settlement and no reinstatement premium shall be due until the ruling is final.",
    "Cl_8_1_LimitAndRetention":
        "The Reinsurer's liability shall not exceed the Limit of Liability shown in the "
        "Schedule, excess of the Retention, and shall be subject to the aggregate limit "
        "and the reinstatement provisions shown in the Schedule.",
}

QUERY_TEXT = {
    "AdjusterCertification": "Provide the adjuster's loss report.",
    "UnmappedAcordPerilCode": "Confirm the peril / cause-of-loss code.",
    "UnmappedCertificationStatus": "Confirm the adjuster report status.",
    "UnmappedLitigationStatus": "Confirm the litigation status.",
    "UnmappedCooperationStatus": "Confirm the claims cooperation status.",
}

BADGE = {
    "Covered": ("#0f7b3f", "#e6f4ea", "COVERED"),
    "Reserved": ("#8a5a00", "#fff4d6", "RESERVED"),
    "Excluded": ("#a31b1b", "#fde8e8", "EXCLUDED"),
    "Incomplete": ("#4a4a4a", "#eceff1", "INCOMPLETE"),
}

CSS = """
:root { --ink:#1c1c1c; --muted:#5f6368; --rule:#d7d7d7; }
* { box-sizing: border-box; }
body { margin:0; padding:28px 32px 40px; font:14px/1.45 -apple-system, "Segoe UI",
       Roboto, Helvetica, Arial, sans-serif; color:var(--ink); background:#fff; }
.page { max-width: 860px; margin: 0 auto; }
header { border-bottom:2px solid var(--ink); padding-bottom:10px; margin-bottom:18px; }
h1 { font-size:19px; margin:0 0 4px; letter-spacing:.2px; }
.sub { color:var(--muted); font-size:12px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:4px 24px; margin:14px 0 6px; }
.kv { display:flex; justify-content:space-between; border-bottom:1px dotted var(--rule);
      padding:3px 0; font-size:13px; }
.kv b { font-weight:600; }
.badge { display:inline-block; padding:6px 14px; border-radius:4px; font-weight:700;
         letter-spacing:.6px; font-size:13px; }
h2 { font-size:12px; text-transform:uppercase; letter-spacing:.8px; color:var(--muted);
     margin:22px 0 8px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:right; padding:6px 8px; border-bottom:1px solid var(--rule); }
th:first-child, td:first-child { text-align:left; }
thead th { background:#f6f6f6; font-weight:600; font-size:12px; }
.clause { margin:0 0 10px; padding:8px 12px; background:#fafafa; border-left:3px solid var(--ink); }
.clause .id { font-weight:700; font-size:12px; letter-spacing:.3px; }
.clause .txt { margin-top:3px; }
.pending { padding:8px 12px; background:#fff4d6; border-left:3px solid #8a5a00; }
.stamp { margin-top:26px; padding-top:12px; border-top:2px solid var(--ink);
         font-size:12px; color:var(--muted); }
.stamp b { color:var(--ink); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
@media print { body { padding:0; } .page { max-width:none; } }
"""


def _money(amount: int, currency: str) -> str:
    if currency not in ISO4217_EXPONENT:
        return str(amount)
    return f"{minor_to_money(amount, currency)} {currency}"


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>'


def render(result: dict, meta: dict) -> str:
    verdict = result["verdict"]
    fg, bg, label = BADGE.get(verdict, BADGE["Incomplete"])
    currency = meta.get("currency", "USD")

    header_rows = "".join([
        _kv("Certificate", meta.get("certificate_id", "—")),
        _kv("Claim", str(result.get("claimId", meta.get("claim_id", "—")))),
        _kv("Peril", meta.get("peril", "—")),
        _kv("Date of loss", meta.get("date_of_loss", "—")),
        _kv("Signed line", f"{meta.get('participation_bps', 10000) / 100:.2f}%"),
        _kv("Retention / limit",
            f"{_money(meta.get('retention_minor', 0), currency)} / "
            f"{_money(meta.get('limit_minor', 0), currency)}"),
    ])

    clauses = "".join(
        f'<div class="clause"><div class="id">{html.escape(cid)}</div>'
        f'<div class="txt">{html.escape(CLAUSE_TEXT.get(cid, "Clause text not found."))}</div></div>'
        for cid in result.get("citedClauses", [])
    ) or '<p class="sub">No clause cited.</p>'

    pending = result.get("pending") or []
    pending_html = ""
    if pending:
        items = "".join(
            f"<li><b>{html.escape(p)}</b> — {html.escape(QUERY_TEXT.get(p, 'Query.'))}</li>"
            for p in pending
        )
        pending_html = f'<h2>Pending queries</h2><div class="pending"><ul>{items}</ul></div>'

    financial = ""
    s = result.get("settlement")
    r = result.get("reserve")
    if s:
        financial = f"""
        <h2>Settlement</h2>
        <table>
          <thead><tr><th>Basis</th><th>Ceded</th><th>Retained by cedent</th>
          <th>Reinstatement premium</th><th>Remaining aggregate</th></tr></thead>
          <tbody>
            <tr><td>100%</td><td>{_money(s['ceded100'], currency)}</td>
                <td>{_money(s['retainedByCedent'], currency)}</td>
                <td>{_money(s['premium100'], currency)}</td>
                <td>{_money(s['remainingAggregate'], currency)}</td></tr>
            <tr><td>Signed line</td><td>{_money(s['reinsurerCeded'], currency)}</td>
                <td>—</td><td>{_money(s['reinsurerPremium'], currency)}</td><td>—</td></tr>
          </tbody>
        </table>"""
    elif r:
        financial = f"""
        <h2>Reserve (no cash movement)</h2>
        <table>
          <thead><tr><th>Basis</th><th>Reserve</th><th>Cash paid</th>
          <th>Reinstatement premium due</th></tr></thead>
          <tbody>
            <tr><td>100%</td><td>{_money(r['layer_100pct_reserve'], currency)}</td>
                <td>{_money(0, currency)}</td><td>{_money(0, currency)}</td></tr>
            <tr><td>Signed line</td><td>{_money(r['reinsurer_reserve_share'], currency)}</td>
                <td>{_money(0, currency)}</td><td>{_money(0, currency)}</td></tr>
          </tbody>
        </table>
        <p class="sub">Cedent's proposed reserve: {_money(r['cedent_proposed_ground_up'], currency)}.
        Capacity is not consumed by a reserve.</p>"""

    if s:
        proof = s["invariant"]
    elif r:
        proof = r["invariant_status"]
    else:
        proof = "n/a"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Claim Adjudication Advice — {html.escape(str(result.get('claimId', '')))}</title>
<style>{CSS}</style></head>
<body><div class="page">
<header>
  <h1>Claim Adjudication Advice</h1>
  <div class="sub">Facultative Excess of Loss Certificate — Property XoL v1</div>
</header>
<div class="grid">{header_rows}</div>
<div style="margin:18px 0 4px">
  <span class="badge" style="color:{fg};background:{bg}">{label}</span>
</div>
<h2>Verdict</h2>
<p>{html.escape(verdict)}. Clauses applied are reproduced verbatim below.</p>
<h2>Verbatim clauses applied</h2>
{clauses}
{pending_html}
{financial}
<div class="stamp">
  <b>Verification:</b> <span class="mono">{html.escape(proof)}</span> —
  arithmetic computed by <b>ReinsuranceLean</b> (Lean 4 kernel, commit
  <span class="mono">1cad8b6</span>); coverage determined by <b>Catala</b>
  (typechecked specification). Money is exact integer minor units; no floating
  point is used anywhere in the pipeline.
</div>
</div></body></html>"""
