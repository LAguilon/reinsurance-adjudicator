# reinsurance-adjudicator

Deterministic claim screening and settlement for a one-layer property
excess-of-loss certificate, split across two formal tools with different jobs.

| Layer | Tool | Guarantee |
|---|---|---|
| Coverage screening | **Catala** (`contracts/*.catala_en`) | the decision is a total function of the claim and the treaty terms; every peril is classified by an exhaustive `match`; verdicts cite typed clauses |
| Settlement arithmetic | **ReinsuranceLean** (`lean_bridge/Runner.lean`) | ceded amount, reinstatement premium and capacity conservation are computed by kernel-checked `Nat` arithmetic |

The screen never computes money. The settlement never decides coverage.

## Verdicts

* **`Covered`** — the peril is insured, the loss is inside the treaty period and
  certified. The claim proceeds to settlement.
* **`Excluded`** — with the exact clause: `Cl_6_1_TreatyPeriod`,
  `Cl_5_1_CyberExclusion`, `Cl_5_2_WarExclusion`, `Cl_4_2_PerilExclusion`.
* **`Incomplete`** — cannot be decided yet: `Cl_7_3_Certification` with pending
  `AdjusterCertification`.

Clause order follows the wording: period, absolute exclusions, scheduled
exclusions, certification, cover.

## Quick start

```bash
# Requires `catala` >= 1.2 on PATH and a stdlib directory (see Environment).
export CATALA=/path/to/catala
export CATALA_STDLIB=/path/to/stdlib      # the directory holding Stdlib_en.catala_en
export CATALA_RUNTIME_SRC=/path/to/runtime # the *.catala_en modules of the runtime
export CATALA_PY_RUNTIME=/path/to/runtime/python/src/catala
./scripts/build.sh          # Catala typecheck + Python backend + Lean bridge
python3 src/cli.py          # human report
python3 src/cli.py --json   # machine-readable audit trail
python3 tests/run_tests.py  # 8 fixtures
```

`catala` is not vendored. Any 1.2+ build works; `clerk` is not required (see
*Environment*).

## Operational guide

See [`docs/FACULTATIVE_GUIDE.md`](docs/FACULTATIVE_GUIDE.md) for the runbook, the
ACORD GRLC mapping tables (ISO 4217 exponents, peril codelist, document
indicators) and the failure modes.

## Layout

```
lakefile.toml                 Lean package; depends on ReinsuranceLean v0.1.0
lean-toolchain                leanprover/lean4:v4.35.0
clerk.toml                    Catala project configuration
contracts/schema.catala_en    Claim, TreatyTerms, Verdict, Peril, Clause, PendingKind
contracts/property_xol_v1.catala_en   the Screen scope
contracts/terms.json          treaty under test
contracts/claims.json         eight sample claims
tests/test_property_xol.catala_en     fixture specification (8 edge cases)
tests/run_tests.py            executes the fixtures (26 assertions)
src/acord_adapter.py          ACORD GRLC ↔ canonical integers
schemas/acord_grlc/           Placing and ClaimMovement samples
docs/FACULTATIVE_GUIDE.md     operations and engineering guide
lean_bridge/Runner.lean       the settlement bridge
src/adjudicator.py            Catala screen + Lean settle + report objects
src/cli.py                    CLI
scripts/build.sh              one-command build
scripts/run_lean.sh           runner wrapper
```

## How the pieces meet

```
claim.json ──► Screen (Catala, compiled to Python)
                   │
                   ├── Excluded / Incomplete ──► audit report (no money)
                   │
                   └── Covered ──► Runner (Lean, ReinsuranceLean)
                                      │
                                      └── ceded, remaining, premium, invariant
```

The bridge is invoked as a subprocess with seven integers and returns four
fields. It re-checks `totalCededPaid + remainingAggregate = limit * (1 +
reinstatements)` at runtime and prints `INVARIANT_OK`; a `VIOLATION` would mean
the bridge called the wrong function, because the theorem rules out the
arithmetic failing.

## What is actually guaranteed

**Verified (kernel).** All money arithmetic comes from `ReinsuranceLean`'s
`layerCeded` and `applyOccurrenceToLayer`, whose properties are proved:
capacity conservation for any sequence of losses, retained + ceded = ground-up
loss, and a zero loss is a no-op. No floating point; `Nat` throughout.

**Checked, not proved.** The coverage decision is a Catala function, typechecked
and exercised by eight fixtures. Catala has no proof obligation here — the
guarantee is that the decision is total, deterministic and cites a typed clause,
not that it matches a statute. The clause texts are placeholders.

**Not modelled.** Occurrence aggregation across claims (the hours clause),
reinstatement premium pro rata as to time, premium ledger, any pricing or
reserving, multi-layer towers, currency. See `ReinsuranceLean`'s own scope note.

## Environment notes

* **Catala.** The build uses the `catala` binary and a stdlib directory. This
  environment used the 1.2.0 `.deb` extracted under `/tmp/catala-root`; the
  runtime library had to be symlinked to `<prefix>/usr/lib/catala`. Nothing
  under `/tmp` is committed: `scripts/build.sh` takes every path from the
  environment variables shown in *Quick start*.
* **`clerk` is not used.** It requires an OCaml toolchain (`zarith`) that is not
  installed here, so `clerk build` and `catala interpret` cannot run. The build
  script therefore drives `catala typecheck` and `catala python` directly and
  assembles the generated modules into a Python package. `tests/test_property_xol.catala_en`
  is written as a fixture specification rather than a live clerk golden test, and
  `tests/run_tests.py` executes the same eight fixtures against the compiled
  backend.
* **Python 3.14 enum equality.** `CatalaEnum.__eq__` in the 1.2.0 runtime passes
  a position argument to `Enum.__eq__`, which Python 3.14 rejects. The contract
  avoids `=` on enum values entirely: perils are classified with `match`, which
  compiles to payload comparison (`p.code == P.Code.A`) and is unaffected. If you
  add a clause that compares enums with `=`, it will fail at runtime.
* **Module files.** Catala module names must match file names, so
  `contracts/schema.catala_en` declares `> Module Schema`; the build concatenates
  the two contract files (headers stripped) because `catala typecheck` accepts a
  single file.

## License

Apache-2.0.
