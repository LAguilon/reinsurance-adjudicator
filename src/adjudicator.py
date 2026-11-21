"""Adjudicator — Catala screening + ReinsuranceLean settlement.

The division of labour is strict:

* Catala decides **coverage**. It returns one of Covered / Excluded /
  Incomplete, with typed clause citations. It never computes money.
* ReinsuranceLean computes **money**. It receives only Covered claims and
  returns exact integer cessions, with the kernel-checked capacity invariant
  re-verified at runtime by the bridge.

Nothing here re-implements either side.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
PKG = BUILD / "pkg"
RUNTIME = Path(
    os.environ.get(
        "CATALA_PY_RUNTIME",
        "/tmp/catala-root/usr/lib/x86_64-linux-gnu/ocaml/5.3.0/catala/runtime/python/src/catala",
    )
)

if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from pkg import property_xol_v1 as catala  # noqa: E402


@dataclass
class Settlement:
    ceded: int
    remaining_aggregate: int
    reinstatement_premium: int
    invariant: str


@dataclass
class Adjudication:
    claim_id: int
    verdict: str
    cited_clauses: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    settlement: Settlement | None = None

    def to_dict(self) -> dict:
        return {
            "claimId": self.claim_id,
            "verdict": self.verdict,
            "citedClauses": self.cited_clauses,
            "pending": self.pending,
            "settlement": None
            if self.settlement is None
            else {
                "ceded": self.settlement.ceded,
                "remainingAggregate": self.settlement.remaining_aggregate,
                "reinstatementPremium": self.settlement.reinstatement_premium,
                "invariant": self.settlement.invariant,
            },
        }


def _enum_name(value) -> str:
    return value.code.name


def screen(claim: dict, terms: dict) -> Adjudication:
    """Run the Catala coverage screen. No money is computed here."""
    c = catala.Claim(
        claimId=claim["claimId"],
        lossAmount=claim["lossAmount"],
        peril=catala.Peril(catala.Peril.Code[claim["peril"]]),
        incidentDay=claim["incidentDay"],
        isCertified=catala.true if claim["isCertified"] else catala.false,
    )
    t = catala.TreatyTerms(
        retention=terms["retention"],
        limit=terms["limit"],
        reinstatements=terms["reinstatements"],
        reinstatementRateBps=terms["reinstatementRateBps"],
        inceptionDay=terms["inceptionDay"],
        expiryDay=terms["expiryDay"],
        excludesFlood=catala.true if terms["excludesFlood"] else catala.false,
        excludesEarthquake=catala.true if terms["excludesEarthquake"] else catala.false,
    )
    out = catala.screen(catala.ScreenIn(claim_in=c, terms_in=t))
    v = out.verdict
    return Adjudication(
        claim_id=claim["claimId"],
        verdict=_enum_name(v.kind),
        cited_clauses=[_enum_name(x) for x in v.citedClauses],
        pending=[_enum_name(x) for x in v.pending],
    )


def settle(claim: dict, terms: dict, runner: str | None = None) -> Settlement:
    """Ask ReinsuranceLean for the cession. Covered claims only."""
    runner = runner or os.environ.get(
        "RUNNER", str(ROOT / "scripts" / "run_lean.sh")
    )
    args = [
        str(terms["retention"]),
        str(terms["limit"]),
        str(terms["reinstatements"]),
        str(terms["reinstatementRateBps"]),
        str(terms.get("remainingAggregate", terms["limit"] * (1 + terms["reinstatements"]))),
        str(terms.get("cededSoFar", 0)),
        str(claim["lossAmount"]),
    ]
    proc = subprocess.run([runner, *args], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"Lean runner failed: {proc.stderr.strip()}")
    parts = proc.stdout.split()
    if len(parts) != 4:
        raise RuntimeError(f"unexpected runner output: {proc.stdout!r}")
    return Settlement(int(parts[0]), int(parts[1]), int(parts[2]), parts[3])


def adjudicate(claim: dict, terms: dict, runner: str | None = None) -> Adjudication:
    result = screen(claim, terms)
    if result.verdict == "Covered":
        result.settlement = settle(claim, terms, runner)
    return result


if __name__ == "__main__":
    terms = json.loads((ROOT / "contracts" / "terms.json").read_text())
    claims = json.loads((ROOT / "contracts" / "claims.json").read_text())
    for claim in claims:
        print(json.dumps(adjudicate(claim, terms).to_dict()))
