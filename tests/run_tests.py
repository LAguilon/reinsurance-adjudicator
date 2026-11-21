"""Fixtures for the internal pipeline and the ACORD GRLC round trip."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import acord_adapter  # noqa: E402
from adjudicator import adjudicate, adjudicate_bordereau  # noqa: E402

TERMS = json.loads((ROOT / "contracts" / "terms.json").read_text())
CLAIMS = {c["claimId"]: c for c in json.loads((ROOT / "contracts" / "claims.json").read_text())}
ACORD = ROOT / "schemas" / "acord_grlc"

PASS, FAIL = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'  ' + detail if detail and not condition else ''}")


def main() -> int:
    # 1-8: coverage screen and settlement on the sample claims
    expected = {1: ("Covered", 7_000_000), 2: ("Covered", 10_000_000), 3: ("Covered", 0),
                4: ("Excluded", None), 5: ("Excluded", None), 6: ("Excluded", None),
                7: ("Excluded", None), 8: ("Incomplete", None)}
    for cid, (verdict, ceded) in expected.items():
        r = adjudicate(CLAIMS[cid], TERMS)
        ok = r.verdict == verdict
        if ceded is not None:
            ok = ok and r.settlement is not None and r.settlement.ceded100 == ceded
        check(f"internal case {cid} -> {verdict}", ok, f"got {r.verdict}")

    # 9: signed line — 25% of the 100% cession
    terms25 = dict(TERMS, participationBps=2500)
    r = adjudicate(CLAIMS[1], terms25)
    check("signed line 25% cedes 1,750,000", r.settlement.reinsurer_ceded == 1_750_000,
          f"got {r.settlement.reinsurer_ceded}")
    check("signed line premium 25% of 7,000,000", r.settlement.reinsurer_premium == 1_750_000,
          f"got {r.settlement.reinsurer_premium}")

    # 10: repeat loss — prior state carried over
    first = adjudicate(CLAIMS[1], TERMS)
    prior = {"remainingAggregate": first.settlement.remaining_aggregate,
             "totalCededPaid": first.settlement.total_ceded_paid}
    second = adjudicate(CLAIMS[2], TERMS, prior)
    check("repeat loss sees reduced capacity", second.settlement.remaining_aggregate == 13_000_000,
          f"got {second.settlement.remaining_aggregate}")
    check("repeat loss conserves total", second.settlement.total_ceded_paid == 17_000_000,
          f"got {second.settlement.total_ceded_paid}")

    # 11: bordereau — sequential, shared capacity
    bord = adjudicate_bordereau([CLAIMS[1], CLAIMS[2], CLAIMS[3]], TERMS)
    check("bordereau cessions 7M, 10M, 0",
          [b.settlement.ceded100 for b in bord] == [7_000_000, 10_000_000, 0])
    check("bordereau final capacity 13M", bord[-1].settlement.remaining_aggregate == 13_000_000,
          f"got {bord[-1].settlement.remaining_aggregate}")

    # 12: ACORD covered round trip
    placing = json.loads((ACORD / "sample_placing.json").read_text())
    claim = json.loads((ACORD / "sample_claim_covered.json").read_text())
    canon = acord_adapter.acord_to_canonical(placing, claim)
    res = adjudicate(canon.as_internal_claim(), canon.as_internal_terms(), flags=canon.flags or None)
    resp = acord_adapter.canonical_to_acord(res.to_dict(), canon)
    check("ACORD covered -> AgreedForSettlement", resp["AdjudicationStatus"] == "AgreedForSettlement")
    check("ACORD 100% ceded is 70,000.00", resp["FinancialSummary"]["Layer100PctCeded"] == "70000.00")
    check("ACORD signed line is 17,500.00", resp["FinancialSummary"]["ReinsurerNetCededShare"] == "17500.00")
    check("ACORD proof verification", resp["FinancialSummary"]["ProofVerification"] == "INVARIANT_OK")
    check("ACORD commit pinned", resp["MessageHeader"]["ReinsuranceLeanCommit"] == "1cad8b6")

    # 13: ACORD incomplete -> PendedQuery
    claim = json.loads((ACORD / "sample_claim_incomplete.json").read_text())
    canon = acord_adapter.acord_to_canonical(placing, claim)
    res = adjudicate(canon.as_internal_claim(), canon.as_internal_terms(), flags=canon.flags or None)
    resp = acord_adapter.canonical_to_acord(res.to_dict(), canon)
    check("ACORD incomplete -> PendedQuery", resp["AdjudicationStatus"] == "PendedQuery")
    check("ACORD incomplete queries the adjuster",
          any(q["QueryCode"] == "AdjusterCertification" for q in resp["PendedQueries"]))

    # 14: unmapped peril is flagged, never guessed
    claim = json.loads((ACORD / "claim_movement_unmapped_peril.json").read_text())
    canon = acord_adapter.acord_to_canonical(placing, claim)
    check("unmapped peril flagged", "UnmappedAcordPerilCode" in canon.flags)
    res = adjudicate(canon.as_internal_claim(), canon.as_internal_terms(), flags=canon.flags or None)
    resp = acord_adapter.canonical_to_acord(res.to_dict(), canon)
    check("unmapped peril -> PendedQuery", resp["AdjudicationStatus"] == "PendedQuery")

    # 15: JPY has exponent 0; 50% signed line
    jp_placing = json.loads((ACORD / "claim_movement_jpy.json").read_text())
    canon = acord_adapter.acord_to_canonical(jp_placing, jp_placing)
    check("JPY minor units are not scaled", canon.total_incurred_minor == 12_000_000,
          f"got {canon.total_incurred_minor}")
    res = adjudicate(canon.as_internal_claim(), canon.as_internal_terms(), flags=canon.flags or None)
    resp = acord_adapter.canonical_to_acord(res.to_dict(), canon)
    check("JPY response has no decimals", resp["FinancialSummary"]["Layer100PctCeded"] == "7000000")

    # 16: floats are rejected at the boundary
    try:
        acord_adapter.money_to_minor(120000.0, "USD", "test")
        check("float rejected", False, "no error raised")
    except acord_adapter.AcordError:
        check("float rejected", True)

    print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} passed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
