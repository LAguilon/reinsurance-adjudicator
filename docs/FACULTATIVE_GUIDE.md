# Facultative adjudication — operational and engineering guide

## 1. What runs where

| Concern | Owner | File |
|---|---|---|
| Coverage decision | Catala | `contracts/property_xol_v1.catala_en` |
| Money | ReinsuranceLean | `lean_bridge/Runner.lean` |
| Wire format | Python | `src/acord_adapter.py` |
| Orchestration | Python | `src/adjudicator.py`, `src/cli.py` |

The boundary is one-way: ACORD JSON → canonical integers → (Catala, Lean) →
canonical result → ACORD JSON. Catala never sees a currency code; Lean never
sees a claim reference.

## 2. Daily operation

```bash
# one claim, internal JSON
python3 src/cli.py --terms contracts/terms.json --claim myclaim.json

# repeat loss: start from where the last audit stopped
python3 src/cli.py --terms contracts/terms.json --claim second.json \
    --prior-audit prior.json

# bordereau: claims share one capacity pool, in file order
python3 src/cli.py --terms contracts/terms.json --bordereau bordereau.json

# ACORD GRLC in, ACORD GRLC out
python3 src/cli.py \
    --acord-placing schemas/acord_grlc/sample_placing.json \
    --acord-claim  schemas/acord_grlc/sample_claim_covered.json \
    --output-acord /tmp/response.json --json
```

`--prior-audit` takes `{"remainingAggregate": N, "totalCededPaid": M}`. Both are
minor units. Omitting it starts from full capacity.

## 3. The verdicts

* `Covered` → settles. `AgreedForSettlement` in ACORD.
* `Excluded` → no settlement. Cites `Cl_6_1_TreatyPeriod`, `Cl_5_1_CyberExclusion`,
  `Cl_5_2_WarExclusion` or `Cl_4_2_PerilExclusion`. `Rejected` in ACORD.
* `Incomplete` → no settlement, a query is raised. `PendedQuery` in ACORD.

Below-attachment losses are **Covered with a zero cession**, not excluded. That
distinction matters for bordereau totals.

## 4. ACORD GRLC mapping

### Currency

Minor units come from the ISO 4217 exponent, not from a guess:

| Exponent | Currencies |
|---|---|
| 0 | JPY, KRW |
| 2 | USD, EUR, GBP, CHF, CAD, AUD, NZD, SEK, NOK, DKK, PLN, CZK, SGD, HKD, CNY, INR, BRL, ZAR, MXN |
| 3 | KWD, BHD, OMR, JOD, TND |

An unlisted currency is a hard error. `Decimal("120000.00")` USD → `12000000`.
A JSON float anywhere in a money field is a hard error: floats cannot represent
cents and are rejected rather than coerced.

### Perils

| ACORD code | Internal |
|---|---|
| `WND`, `WINDSTORM`, `STORM` | Windstorm |
| `FLD`, `FLOOD`, `INUNDATION` | Flood |
| `EQ`, `EQK`, `EARTHQUAKE` | Earthquake |
| `FIR`, `FIRE` | Fire |
| `CYB`, `CYBER` | Cyber |
| `WAR`, `TRM`, `TERRORISM` | War |

Anything else raises `UnmappedAcordPerilCode` and the claim is **pended, not
guessed**. Add codes to `ACORD_PERIL_TO_INTERNAL` in `src/acord_adapter.py`; the
Catala side needs a matching `Peril` constructor.

### Document indicators

`LossAdjusterReportStatus`, `LitigationStatus`, `ClaimsCooperationStatus` map to
`True` / `False` / `None`:

* `COMPLETED`, `FINAL`, `RECEIVED`, `AGREED`, `COMPLETE` → `True`
* `PENDING`, `NOTRECEIVED`, `OUTSTANDING`, `REQUESTED`, `OPEN` → `False`
* `NONE`, `NA`, `N/A`, `NOTAPPLICABLE` → `False` (no adverse indicator)
* anything else → `None`, which pends the claim with `UnmappedCertificationStatus`

Only the adjuster status drives certification. Litigation and cooperation are
carried in the audit trail but do not block settlement today.

## 5. Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `AcordError: raw JSON float` | a number was sent unquoted | send the decimal as a string |
| `AcordError: sub-minor-unit precision` | e.g. `"10.001"` USD | round at source, never here |
| `AcordError: unsupported ISO 4217` | currency not in the table | add the exponent deliberately |
| `PendedQuery` with `UnmappedAcordPerilCode` | unknown cause-of-loss | extend the codelist |
| `VIOLATION` from the runner | bridge called the wrong function | stop; the kernel proves it cannot happen |

## 6. Engineering rules

1. **No float** in `src/`, ever. `Decimal` in, `int` out.
2. **No ACORD key** outside `src/acord_adapter.py`. If a new field is needed,
   add it to `CanonicalClaim` and map it there.
3. **No money in Catala**, no coverage logic in Lean. The split is the point.
4. **Perils are exhaustive in Catala.** Adding a constructor to `Peril` breaks
   the build until every `match` classifies it. That is deliberate.
5. **Never `=` on Catala enums.** The 1.2 runtime's `CatalaEnum.__eq__` is
   incompatible with Python 3.14; `match` compiles to payload comparison and is
   safe. This is why the contract is written with `match`.
6. **Signed line is applied last**, to the 100% figures, with `applyBps`. Never
   scale the loss first: `applyBps` floors, and flooring early loses cents.

## 7. What is not modelled

Occurrence aggregation across claims (hours clause), reinstatement premium pro
rata as to time, premium ledger, multi-layer towers, currency conversion,
discounting. A `bordereau` is a sequence of independent occurrences sharing one
capacity pool — it is not an aggregation rule.
