/-
  Runner — the verified settlement bridge.

  Reads one claim's numbers on the command line, applies the layer using
  `ReinsuranceLean.applyOccurrenceToLayer`, and prints the settlement. The
  arithmetic is entirely `ReinsuranceLean`'s; this file only parses and prints.

  Usage:
    Runner <retention> <limit> <reinstatements> <rateBps>
           <remainingAggregate> <cededSoFar> <loss>

  Output (one line):
    <cededThisEvent> <remainingAggregate'> <premiumTotal'> <INVARIANT_OK|VIOLATION>
-/
import ReinsuranceLean

open ReinsuranceLean

def parseNat (s : String) : Nat := (s.toNat?).getD 0

def main (args : List String) : IO Unit := do
  match args with
  | [retS, limS, reS, rateS, remS, cedS, lossS] =>
    let layer : XoLLayer :=
      { name := "screened-layer"
        retention := parseNat retS
        limit := parseNat limS
        reinstatements := parseNat reS
        reinstatementRateBps := parseNat rateS
        proRataTime := false }
    let st : TreatyState :=
      { remainingAggregate := parseNat remS
        totalCededPaid := parseNat cedS
        totalRetainedByCedent := 0
        reinstatementPremiumPaid := 0 }
    let st' := applyOccurrenceToLayer layer st (parseNat lossS)
    let ceded := st'.totalCededPaid - st.totalCededPaid
    -- Belt and braces: the kernel proves this, but the bridge should not be
    -- trusted to have called the right function.
    let cap := layer.limit * (1 + layer.reinstatements)
    let ok := decide (st'.totalCededPaid + st'.remainingAggregate = cap)
    IO.println s!"{ceded} {st'.remainingAggregate} {st'.reinstatementPremiumPaid} {if ok then "INVARIANT_OK" else "VIOLATION"}"
  | _ =>
    IO.eprintln "usage: Runner <retention> <limit> <reinstatements> <rateBps> <remaining> <cededSoFar> <loss>"
    IO.Process.exit 2
