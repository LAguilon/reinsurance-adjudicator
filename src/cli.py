"""Command-line entry point for the adjudicator."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from adjudicator import adjudicate  # noqa: E402


def human(results) -> str:
    lines = []
    for r in results:
        head = f"claim {r.claim_id}: {r.verdict}"
        if r.cited_clauses:
            head += "  [" + ", ".join(r.cited_clauses) + "]"
        lines.append(head)
        if r.pending:
            lines.append(f"    pending: {', '.join(r.pending)}")
        if r.settlement:
            s = r.settlement
            lines.append(
                f"    ceded {s.ceded}  remaining {s.remaining_aggregate}"
                f"  reinstatement premium {s.reinstatement_premium}  {s.invariant}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Screen claims with Catala, settle with ReinsuranceLean.")
    ap.add_argument("--terms", default=str(ROOT / "contracts" / "terms.json"))
    ap.add_argument("--claims", default=str(ROOT / "contracts" / "claims.json"))
    ap.add_argument("--claim", type=int, help="adjudicate a single claim id")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    terms = json.loads(Path(args.terms).read_text())
    claims = json.loads(Path(args.claims).read_text())
    if args.claim is not None:
        claims = [c for c in claims if c["claimId"] == args.claim]
        if not claims:
            print(f"no claim with id {args.claim}", file=sys.stderr)
            return 2

    results = [adjudicate(c, terms) for c in claims]
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(human(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
