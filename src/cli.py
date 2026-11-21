"""Command-line entry point for the adjudicator."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import acord_adapter  # noqa: E402
import report  # noqa: E402
from adjudicator import adjudicate, adjudicate_bordereau  # noqa: E402
from datetime import date, timedelta  # noqa: E402

EPOCH = date(1970, 1, 1)


def day_to_iso(day: int) -> str:
    return (EPOCH + timedelta(days=day)).isoformat()


def meta_from_canonical(canon) -> dict:
    return {
        "certificate_id": canon.certificate_id,
        "claim_id": canon.claim_id,
        "currency": canon.currency,
        "participation_bps": canon.participation_bps,
        "retention_minor": canon.retention_minor,
        "limit_minor": canon.limit_minor,
        "peril": canon.peril or "—",
        "date_of_loss": day_to_iso(canon.date_of_loss),
    }


def meta_from_internal(claim: dict, terms: dict) -> dict:
    return {
        "certificate_id": terms.get("certificateId", "—"),
        "claim_id": str(claim.get("claimId", "—")),
        "currency": terms.get("currency", "USD"),
        "participation_bps": terms.get("participationBps", 10000),
        "retention_minor": terms["retention"],
        "limit_minor": terms["limit"],
        "peril": claim.get("peril", "—"),
        "date_of_loss": day_to_iso(claim["incidentDay"]),
    }


def human(results) -> str:
    lines = []
    for r in results:
        head = f"claim {r.claim_id}: {r.verdict}"
        if r.cited_clauses:
            head += "  [" + ", ".join(r.cited_clauses) + "]"
        lines.append(head)
        if r.pending:
            lines.append(f"    pending: {', '.join(r.pending)}")
        if r.reserve:
            v = r.reserve
            lines.append(
                f"    reserve proposed {v.cedent_proposed_ground_up}"
                f"  100% {v.layer_100pct_reserve}"
                f"  signed line {v.reinsurer_reserve_share}  {v.invariant_status}"
            )
        if r.settlement:
            s = r.settlement
            lines.append(
                f"    100% ceded {s.ceded100}  retained {s.retained_by_cedent}"
                f"  premium {s.premium100}  remaining {s.remaining_aggregate}"
            )
            lines.append(
                f"    signed line {s.reinsurer_ceded} ceded"
                f"  {s.reinsurer_premium} premium  {s.invariant}"
            )
    return "\n".join(lines)


def load(path: str):
    return json.loads(Path(path).read_text())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Screen claims with Catala, settle with ReinsuranceLean.")
    ap.add_argument("--terms", default=str(ROOT / "contracts" / "terms.json"))
    ap.add_argument("--claims", default=str(ROOT / "contracts" / "claims.json"))
    ap.add_argument("--claim", help="adjudicate a single internal claim file")
    ap.add_argument("--bordereau", help="sequential bordereau: claims share capacity")
    ap.add_argument("--prior-audit", help="prior state {remainingAggregate,totalCededPaid}")
    ap.add_argument("--acord-placing", help="ACORD GRLC Placing JSON")
    ap.add_argument("--acord-claim", help="ACORD GRLC ClaimMovement JSON")
    ap.add_argument("--output-acord", help="write the ACORD response to this file")
    ap.add_argument("--claim-id", help="adjudicate one claim id from --claims")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report-html", help="write a one-page HTML advice to this path")
    args = ap.parse_args(argv)

    prior = load(args.prior_audit) if args.prior_audit else None

    if args.acord_placing and args.acord_claim:
        placing = load(args.acord_placing)
        claim = load(args.acord_claim)
        canonical = acord_adapter.acord_to_canonical(placing, claim)
        result = adjudicate(
            canonical.as_internal_claim(),
            canonical.as_internal_terms(),
            prior,
            flags=canonical.flags or None,
            proposed_reserve=canonical.proposed_reserve_minor,
        )
        response = acord_adapter.canonical_to_acord(result.to_dict(), canonical)
        if args.output_acord:
            Path(args.output_acord).write_text(json.dumps(response, indent=2) + "\n")
        if args.report_html:
            page = report.render(result.to_dict(), meta_from_canonical(canonical))
            Path(args.report_html).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report_html).write_text(page)
            print(f"advice written to {args.report_html}", file=sys.stderr)
        print(json.dumps(response, indent=2) if args.json else human([result]))
        return 0

    if args.acord_placing or args.acord_claim:
        print("both --acord-placing and --acord-claim are required", file=sys.stderr)
        return 2

    terms = load(args.terms)

    if args.claim:
        single = load(args.claim)
        if not isinstance(single, dict):
            print("--claim expects a single claim object, not a list", file=sys.stderr)
            return 2
        results = [adjudicate(single, terms, prior,
                              proposed_reserve=single.get("proposedReserve"))]
    elif args.bordereau:
        results = adjudicate_bordereau(load(args.bordereau), terms, prior)
    else:
        claims = load(args.claims)
        if args.claim_id is not None:
            claims = [c for c in claims if str(c["claimId"]) == str(args.claim_id)]
            if not claims:
                print(f"no claim with id {args.claim_id}", file=sys.stderr)
                return 2
        results = [adjudicate(c, terms, prior,
                              proposed_reserve=c.get("proposedReserve")) for c in claims]

    if args.report_html:
        if len(results) != 1:
            print("--report-html needs exactly one claim; use --claim or --claim-id",
                  file=sys.stderr)
            return 2
        meta = meta_from_internal(
            load(args.claim) if args.claim else claims[0], terms
        )
        page = report.render(results[0].to_dict(), meta)
        Path(args.report_html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_html).write_text(page)
        print(f"advice written to {args.report_html}", file=sys.stderr)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(human(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
