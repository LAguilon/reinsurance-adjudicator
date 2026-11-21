"""Execute the eight fixtures in tests/test_property_xol.catala_en."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from adjudicator import adjudicate  # noqa: E402

TERMS = json.loads((ROOT / "contracts" / "terms.json").read_text())

CASES = [
    (1, "Covered", 7_000_000),
    (2, "Covered", 10_000_000),
    (3, "Covered", 0),
    (4, "Excluded", None),
    (5, "Excluded", None),
    (6, "Excluded", None),
    (7, "Excluded", None),
    (8, "Incomplete", None),
]

def main() -> int:
    claims = {c["claimId"]: c for c in json.loads((ROOT / "contracts" / "claims.json").read_text())}
    failures = 0
    for claim_id, expected_verdict, expected_ceded in CASES:
        result = adjudicate(claims[claim_id], TERMS)
        ok = result.verdict == expected_verdict
        detail = result.verdict
        if expected_ceded is not None:
            got = result.settlement.ceded if result.settlement else None
            ok = ok and got == expected_ceded
            detail += f" ceded={got}"
        if not ok:
            failures += 1
        print(f"case {claim_id}: {'PASS' if ok else 'FAIL'} ({detail})")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
