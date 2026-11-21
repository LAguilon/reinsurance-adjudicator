"""Adjudicator — Catala screening + ReinsuranceLean settlement.

Catala decides coverage and never computes money. ReinsuranceLean computes money
and never decides coverage. This module is the only place that knows both, and
it knows nothing about ACORD.
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
    ceded100: int
    retained_by_cedent: int
    premium100: int
    total_ceded_paid: int
    remaining_aggregate: int
    reinsurer_ceded: int
    reinsurer_premium: int
    invariant: str

    def to_dict(self) -> dict:
        return {
            "ceded100": self.ceded100,
            "retainedByCedent": self.retained_by_cedent,
            "premium100": self.premium100,
            "totalCededPaid": self.total_ceded_paid,
            "remainingAggregate": self.remaining_aggregate,
            "reinsurerCeded": self.reinsurer_ceded,
            "reinsurerPremium": self.reinsurer_premium,
            "invariant": self.invariant,
        }


@dataclass
class Reserve:
    """A booked reserve on an unresolved court ruling: no cash, no premium."""

    cedent_proposed_ground_up: int
    layer_100pct_reserve: int
    reinsurer_reserve_share: int
    invariant_status: str

    def to_dict(self) -> dict:
        return {
            "cedent_proposed_ground_up": self.cedent_proposed_ground_up,
            "layer_100pct_reserve": self.layer_100pct_reserve,
            "reinsurer_reserve_share": self.reinsurer_reserve_share,
            "invariant_status": self.invariant_status,
        }


@dataclass
class StateAfter:
    total_ceded_paid: int
    remaining_aggregate: int
    ceded_reserved_100pct: int
    reinsurer_ceded_reserved: int

    def to_dict(self) -> dict:
        return {
            "total_ceded_paid": self.total_ceded_paid,
            "remaining_aggregate": self.remaining_aggregate,
            "ceded_reserved_100pct": self.ceded_reserved_100pct,
            "reinsurer_ceded_reserved": self.reinsurer_ceded_reserved,
        }


@dataclass
class Adjudication:
    claim_id: str
    verdict: str
    cited_clauses: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    settlement: Settlement | None = None
    reserve: Reserve | None = None
    state_after: StateAfter | None = None

    def to_dict(self) -> dict:
        return {
            "claimId": self.claim_id,
            "verdict": self.verdict,
            "citedClauses": self.cited_clauses,
            "pending": self.pending,
            "settlement": None if self.settlement is None else self.settlement.to_dict(),
            "reserve": None if self.reserve is None else self.reserve.to_dict(),
            "state_after": None if self.state_after is None else self.state_after.to_dict(),
        }


def _enum_name(value) -> str:
    return value.code.name


def screen(claim: dict, terms: dict) -> Adjudication:
    """Catala coverage screen. Money is not touched."""
    c = catala.Claim(
        lossAmount=claim["lossAmount"],
        peril=catala.Peril(catala.Peril.Code[claim["peril"]]),
        incidentDay=claim["incidentDay"],
        isCertified=catala.true if claim["isCertified"] else catala.false,
        litigationFinal=catala.true if claim.get("litigationFinal", True) else catala.false,
        resultingFireOrExplosion=catala.true
        if claim.get("resultingFireOrExplosion", False)
        else catala.false,
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


def settle(
    claim: dict,
    terms: dict,
    prior: dict | None = None,
    runner: str | None = None,
) -> Settlement:
    """Ask ReinsuranceLean for the 100% figures and the signed-line share."""
    runner = runner or os.environ.get("RUNNER", str(ROOT / "scripts" / "run_lean.sh"))
    prior = prior or {}
    cap = terms["limit"] * (1 + terms["reinstatements"])
    args = [
        str(terms["retention"]),
        str(terms["limit"]),
        str(terms["reinstatements"]),
        str(terms["reinstatementRateBps"]),
        str(prior.get("remainingAggregate", cap)),
        str(prior.get("totalCededPaid", 0)),
        str(claim["lossAmount"]),
        str(terms.get("participationBps", 10000)),
    ]
    proc = subprocess.run([runner, *args], capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"Lean runner failed: {proc.stderr.strip() or proc.stdout.strip()}")
    parts = proc.stdout.split()
    if len(parts) != 8:
        raise RuntimeError(f"unexpected runner output: {proc.stdout!r}")
    return Settlement(
        ceded100=int(parts[0]),
        retained_by_cedent=int(parts[1]),
        premium100=int(parts[2]),
        total_ceded_paid=int(parts[3]),
        remaining_aggregate=int(parts[4]),
        reinsurer_ceded=int(parts[5]),
        reinsurer_premium=int(parts[6]),
        invariant=parts[7],
    )


def _prior_state(terms: dict, prior: dict | None) -> tuple[int, int]:
    cap = terms["limit"] * (1 + terms["reinstatements"])
    prior = prior or {}
    return prior.get("remainingAggregate", cap), prior.get("totalCededPaid", 0)


def adjudicate(
    claim: dict,
    terms: dict,
    prior: dict | None = None,
    runner: str | None = None,
    flags: list[str] | None = None,
    proposed_reserve: int | None = None,
) -> Adjudication:
    """Screen, then settle (Covered) or book a reserve (Reserved).

    `flags` come from the ACORD adapter; `proposed_reserve` is the cedent's
    outstanding loss reserve in minor units, used only when the verdict is
    Reserved.
    """
    remaining, paid = _prior_state(terms, prior)

    if flags:
        return Adjudication(
            claim_id=claim["claimId"],
            verdict="Incomplete",
            cited_clauses=[],
            pending=list(flags),
            state_after=StateAfter(paid, remaining, 0, 0),
        )

    result = screen(claim, terms)

    if result.verdict == "Covered":
        result.settlement = settle(claim, terms, prior, runner)
        result.state_after = StateAfter(
            result.settlement.total_ceded_paid,
            result.settlement.remaining_aggregate,
            0,
            0,
        )
    elif result.verdict == "Reserved":
        amount = claim["lossAmount"] if proposed_reserve is None else proposed_reserve
        # The layer arithmetic is the same function; only the reporting differs.
        booked = settle(dict(claim, lossAmount=amount), terms, prior, runner)
        result.reserve = Reserve(
            cedent_proposed_ground_up=amount,
            layer_100pct_reserve=booked.ceded100,
            reinsurer_reserve_share=booked.reinsurer_ceded,
            invariant_status=booked.invariant,
        )
        # Cash pool untouched: no cession paid, no capacity consumed.
        result.state_after = StateAfter(paid, remaining, booked.ceded100, booked.reinsurer_ceded)
    else:
        result.state_after = StateAfter(paid, remaining, 0, 0)
    return result


def adjudicate_bordereau(
    claims: list[dict],
    terms: dict,
    prior: dict | None = None,
    runner: str | None = None,
) -> list[Adjudication]:
    """Sequential bordereau: each claim starts where the previous one ended."""
    state = dict(prior or {})
    cap = terms["limit"] * (1 + terms["reinstatements"])
    state.setdefault("remainingAggregate", cap)
    state.setdefault("totalCededPaid", 0)
    results = []
    for claim in claims:
        result = adjudicate(claim, terms, state, runner)
        results.append(result)
        if result.settlement is not None:
            state["remainingAggregate"] = result.settlement.remaining_aggregate
            state["totalCededPaid"] = result.settlement.total_ceded_paid
    return results
