/-
  Runner — the verified settlement bridge.

  Applies one occurrence to a layer using `ReinsuranceLean.applyOccurrenceToLayer`
  (100% layer arithmetic), then takes the reinsurer's signed-line share with
  `ReinsuranceLean.applyBps`. Every number below is `Nat` minor units or basis
  points; there is no floating point and no external dependency.

  Usage:
    Runner <retention> <limit> <reinstatements> <rateBps>
           <remainingAggregate> <priorCededPaid> <loss> <participationBps>

  Output (one line, space separated):
    <ceded100> <retainedByCedent> <premium100> <totalCededPaid>
    <remainingAggregate> <reinsurerCeded> <reinsurerPremium> <STATUS>

  STATUS is `INVARIANT_OK` or `VIOLATION`; a violation exits non-zero, because
  the kernel proves the invariant and a failure means this bridge called the
  wrong function.
-/
import ReinsuranceLean

open ReinsuranceLean

def parseNat (s : String) : Nat := (s.toNat?).getD 0

def main (args : List String) : IO Unit := do
  match args with
  | [retS, limS, reS, rateS, remS, priorS, lossS, partS] =>
    let retention := parseNat retS
    let limit := parseNat limS
    let reinstatements := parseNat reS
    let rateBps := parseNat rateS
    let remaining := parseNat remS
    let priorCeded := parseNat priorS
    let loss := parseNat lossS
    let participationBps := parseNat partS
    let layer : XoLLayer :=
      { name := "screened-layer"
        retention := retention
        limit := limit
        reinstatements := reinstatements
        reinstatementRateBps := rateBps
        proRataTime := false }
    let st : TreatyState :=
      { remainingAggregate := remaining
        totalCededPaid := priorCeded
        totalRetainedByCedent := 0
        reinstatementPremiumPaid := 0 }
    let st' := applyOccurrenceToLayer layer st loss
    let ceded100 := st'.totalCededPaid - st.totalCededPaid
    let premium100 := st'.reinstatementPremiumPaid - st.reinstatementPremiumPaid
    -- Signed line: the reinsurer's share of the 100% figures.
    let reinsurerCeded := applyBps ceded100 participationBps
    let reinsurerPremium := applyBps premium100 participationBps
    let cap := limit * (1 + reinstatements)
    let ok := decide (st'.totalCededPaid + st'.remainingAggregate = cap)
    let status := if ok then "INVARIANT_OK" else "VIOLATION"
    IO.println s!"{ceded100} {st'.totalRetainedByCedent} {premium100} \
      {st'.totalCededPaid} {st'.remainingAggregate} {reinsurerCeded} \
      {reinsurerPremium} {status}"
    if !ok then IO.Process.exit 3
  | _ =>
    IO.eprintln "usage: Runner <retention> <limit> <reinstatements> <rateBps> \
      <remaining> <priorCeded> <loss> <participationBps>"
    IO.Process.exit 2
