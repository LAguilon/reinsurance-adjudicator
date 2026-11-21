"""ACORD GRLC anti-corruption layer.

Everything ACORD-shaped stops here. The adapter converts inbound GRLC Placing
and ClaimMovement (ECOT) JSON into canonical integer types for Catala and
ReinsuranceLean, and converts the verified result back into a GRLC
ClaimMovementResponse (EBOT advice).

Rules enforced here:

* Money is `Decimal` from a JSON **string**, scaled by the ISO 4217 exponent to
  `int` minor units. Raw JSON floats are rejected: they cannot represent cents
  exactly and must not enter the pipeline.
* Percentages are `Decimal` strings; basis points are `int(percent * 100)`.
* Peril codes go through an explicit codelist. An unknown code is **not
  guessed**: the claim is flagged and routed to `Incomplete`.
* No float and no ACORD key ever reaches Catala or Lean.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

ISO4217_EXPONENT = {
    "USD": 2, "EUR": 2, "GBP": 2, "CHF": 2, "CAD": 2, "AUD": 2, "NZD": 2,
    "SEK": 2, "NOK": 2, "DKK": 2, "PLN": 2, "CZK": 2, "SGD": 2, "HKD": 2,
    "CNY": 2, "INR": 2, "BRL": 2, "ZAR": 2, "MXN": 2,
    "JPY": 0, "KRW": 0,
    "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3, "TND": 3,
}

# ACORD cause-of-loss / peril codes → Catala `Peril`. The real GRLC codelists
# are licensed; these are the codes this adapter recognises. Anything else is
# flagged, never guessed.
ACORD_PERIL_TO_INTERNAL = {
    "WND": "Windstorm", "WINDSTORM": "Windstorm", "STORM": "Windstorm",
    "FLD": "Flood", "FLOOD": "Flood", "INUNDATION": "Flood",
    "EQ": "Earthquake", "EQK": "Earthquake", "EARTHQUAKE": "Earthquake",
    "FIR": "Fire", "FIRE": "Fire",
    "CYB": "Cyber", "CYBER": "Cyber",
    "WAR": "War", "TRM": "War", "TERRORISM": "War",
}

CERTIFIED_STATUSES = {"COMPLETED", "FINAL", "RECEIVED", "AGREED", "COMPLETE"}

# LitigationStatus: does an unresolved court ruling block cash settlement?
LITIGATION_FINAL = {"FINAL", "SETTLED", "NONE", "NA", "N/A", "NOTAPPLICABLE"}
LITIGATION_OPEN = {"PENDING", "OPEN", "ACTIVE", "ONGOING", "UNRESOLVED"}
PENDING_STATUSES = {"PENDING", "NOTRECEIVED", "OUTSTANDING", "REQUESTED", "OPEN"}
NEUTRAL_STATUSES = {"NONE", "NA", "N/A", "NOTAPPLICABLE", "NOTAPPLICABLE", "NO"}

EPOCH = date(1970, 1, 1)


class AcordError(ValueError):
    """Raised when a payload cannot be mapped without guessing."""


def _reject_float(value, where: str) -> None:
    if isinstance(value, float):
        raise AcordError(f"{where}: raw JSON float is not acceptable; send a decimal string")


def money_to_minor(value, currency: str, where: str) -> int:
    _reject_float(value, where)
    if currency not in ISO4217_EXPONENT:
        raise AcordError(f"{where}: unsupported or unknown ISO 4217 currency {currency!r}")
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise AcordError(f"{where}: {value!r} is not a decimal number") from exc
    scaled = d.scaleb(ISO4217_EXPONENT[currency])
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise AcordError(f"{where}: {value!r} {currency} has sub-minor-unit precision")
    return int(integral)


def minor_to_money(amount: int, currency: str) -> str:
    exp = ISO4217_EXPONENT.get(currency)
    if exp is None:
        raise AcordError(f"unsupported ISO 4217 currency {currency!r}")
    return str(Decimal(amount).scaleb(-exp).quantize(Decimal(1).scaleb(-exp)))


def percent_to_bps(value, where: str) -> int:
    _reject_float(value, where)
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise AcordError(f"{where}: {value!r} is not a percentage") from exc
    bps = d * 100
    integral = bps.to_integral_value()
    if bps != integral:
        raise AcordError(f"{where}: {value!r}% is finer than one basis point")
    if integral < 0:
        raise AcordError(f"{where}: negative percentage")
    return int(integral)


def iso_date_to_day(value: str, where: str) -> int:
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise AcordError(f"{where}: {value!r} is not an ISO date") from exc
    return (d - EPOCH).days


def map_peril(code: str | None) -> str | None:
    return None if code is None else ACORD_PERIL_TO_INTERNAL.get(str(code).strip().upper())


def map_flag(value, where: str) -> bool:
    """Strict boolean: JSON true/false or null. Anything else is an error."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    raise AcordError(f"{where}: expected a JSON boolean, got {value!r}")


def map_litigation(value: str | None) -> bool | None:
    """LitigationStatus → True (no unresolved ruling) / False / None (unknown)."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if s in LITIGATION_FINAL:
        return True
    if s in LITIGATION_OPEN:
        return False
    return None


def map_indicator(value: str | None) -> bool | None:
    """Document indicator → True / False / None (unknown)."""
    if value is None:
        return None
    s = str(value).strip().upper()
    if s in CERTIFIED_STATUSES:
        return True
    if s in PENDING_STATUSES:
        return False
    if s in NEUTRAL_STATUSES:
        return False  # no adverse indicator, and not an unknown value
    return None


@dataclass
class CanonicalClaim:
    """The only shape the rest of the pipeline sees."""

    certificate_id: str
    claim_id: str
    currency: str
    retention_minor: int
    limit_minor: int
    participation_bps: int
    reinstatements: int
    reinstatement_rate_bps: int
    period_start: int
    period_end: int
    total_incurred_minor: int
    date_of_loss: int
    peril: str | None
    certified: bool | None
    litigation_final: bool | None = True
    resulting_fire_or_explosion: bool = False
    proposed_reserve_minor: int | None = None
    excludes_flood: bool = True
    excludes_earthquake: bool = True
    document_indicators: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.flags

    def as_internal_claim(self) -> dict:
        return {
            "claimId": self.claim_id,
            "lossAmount": self.total_incurred_minor,
            "peril": self.peril or "Windstorm",
            "incidentDay": self.date_of_loss,
            "isCertified": bool(self.certified),
            "litigationFinal": bool(self.litigation_final),
            "resultingFireOrExplosion": self.resulting_fire_or_explosion,
        }

    def as_internal_terms(self) -> dict:
        return {
            "retention": self.retention_minor,
            "limit": self.limit_minor,
            "reinstatements": self.reinstatements,
            "reinstatementRateBps": self.reinstatement_rate_bps,
            "inceptionDay": self.period_start,
            "expiryDay": self.period_end,
            "excludesFlood": self.excludes_flood,
            "excludesEarthquake": self.excludes_earthquake,
            "participationBps": self.participation_bps,
        }


def acord_to_canonical(placing: dict, claim: dict) -> CanonicalClaim:
    """Inbound GRLC Placing + ClaimMovement → canonical integers."""
    try:
        contract = placing["Contract"]
        movement = claim["ClaimMovement"]
    except KeyError as exc:
        raise AcordError(f"missing top-level section {exc}") from exc

    layer = contract["Layer"]
    currency = layer.get("CurrencyCode") or movement.get("FinancialAmounts", {}).get("CurrencyCode")
    if currency is None:
        raise AcordError("no CurrencyCode on the layer or the claim")

    period = contract["CoveragePeriod"]
    reinst = contract.get("ReinstatementProvisions", {})
    amounts = movement["FinancialAmounts"]
    indicators = dict(movement.get("DocumentIndicators", {}))
    # Some ECOT variants put the adjuster status at the top level of the
    # movement rather than under DocumentIndicators; accept both shapes.
    for key in ("LossAdjusterReportStatus", "LitigationStatus", "ClaimsCooperationStatus"):
        if key in movement and key not in indicators:
            indicators[key] = movement[key]
    certified = map_indicator(indicators.get("LossAdjusterReportStatus"))
    litigation = (
        map_litigation(indicators["LitigationStatus"])
        if "LitigationStatus" in indicators
        else True  # no litigation indicator means no known ruling
    )
    proposed = amounts.get("OutstandingLossReserve")

    flags: list[str] = []
    peril = map_peril(movement.get("CauseOfLossCode") or movement.get("PerilCode"))
    if peril is None:
        flags.append("UnmappedAcordPerilCode")
    if certified is None:
        flags.append("UnmappedCertificationStatus")
    if "LitigationStatus" in indicators and litigation is None:
        flags.append("UnmappedLitigationStatus")
    if "ClaimsCooperationStatus" in indicators and map_indicator(indicators["ClaimsCooperationStatus"]) is None:
        flags.append("UnmappedCooperationStatus")

    return CanonicalClaim(
        certificate_id=contract.get("ContractReference", ""),
        claim_id=movement.get("ClaimReference", ""),
        currency=currency,
        retention_minor=money_to_minor(layer["AttachmentPoint"], currency, "Layer.AttachmentPoint"),
        limit_minor=money_to_minor(layer["Limit"], currency, "Layer.Limit"),
        participation_bps=percent_to_bps(
            contract["MarketParticipation"]["SignedLinePercentage"],
            "MarketParticipation.SignedLinePercentage",
        ),
        reinstatements=int(reinst.get("Count", 0)),
        reinstatement_rate_bps=percent_to_bps(
            reinst.get("RatePercentage", "0"), "ReinstatementProvisions.RatePercentage"
        ),
        period_start=iso_date_to_day(period["StartDate"], "CoveragePeriod.StartDate"),
        period_end=iso_date_to_day(period["EndDate"], "CoveragePeriod.EndDate"),
        total_incurred_minor=money_to_minor(
            amounts["TotalIncurred"], currency, "FinancialAmounts.TotalIncurred"
        ),
        date_of_loss=iso_date_to_day(movement["DateOfLoss"], "ClaimMovement.DateOfLoss"),
        peril=peril,
        certified=certified,
        litigation_final=litigation,
        resulting_fire_or_explosion=map_flag(
            (movement.get("LossDetails") or {}).get(
                "ResultingFireOrExplosion",
                indicators.get("ResultingFireOrExplosion",
                              movement.get("ResultingFireOrExplosion")),
            ),
            "LossDetails.ResultingFireOrExplosion",
        ),
        proposed_reserve_minor=None
        if proposed is None
        else money_to_minor(proposed, currency, "FinancialAmounts.OutstandingLossReserve"),
        excludes_flood=bool(contract.get("Exclusions", {}).get("Flood", True)),
        excludes_earthquake=bool(contract.get("Exclusions", {}).get("Earthquake", True)),
        document_indicators=dict(indicators),
        flags=flags,
    )


ADJUDICATION_STATUS = {
    "Covered": "AgreedForSettlement",
    "Reserved": "ReserveAdvised",
    "Excluded": "Rejected",
    "Incomplete": "PendedQuery",
}

QUERY_TEXT = {
    "AdjusterCertification": "Provide the adjuster's loss report",
    "UnmappedAcordPerilCode": "Confirm the peril / cause-of-loss code",
    "UnmappedCertificationStatus": "Confirm the adjuster report status",
    "UnmappedLitigationStatus": "Confirm the litigation status",
    "UnmappedCooperationStatus": "Confirm the claims cooperation status",
}


def canonical_to_acord(result: dict, canonical: CanonicalClaim, commit: str = "1cad8b6") -> dict:
    """Verified adjudication → GRLC ClaimMovementResponse (EBOT advice)."""
    body: dict = {
        "MessageHeader": {
            "MessageType": "ClaimMovementResponse",
            "StandardVersion": "ACORD-GRLC-Gen2",
            "ContractReference": canonical.certificate_id,
            "ClaimReference": canonical.claim_id,
            "ReinsuranceLeanCommit": commit,
        },
        "AdjudicationStatus": ADJUDICATION_STATUS[result["verdict"]],
        "ClauseCitations": list(result.get("citedClauses", [])),
        "PendedQueries": [
            {"QueryCode": q, "QueryText": QUERY_TEXT.get(q, q)}
            for q in (result.get("pending") or [])
        ],
    }
    if result["verdict"] == "Reserved":
        r = result["reserve"]
        body["ReserveSummary"] = {
            "CurrencyCode": canonical.currency,
            "CedentProposedReserve": minor_to_money(r["cedent_proposed_ground_up"], canonical.currency),
            "Layer100PctCededReserve": minor_to_money(r["layer_100pct_reserve"], canonical.currency),
            "ReinsurerNetCededReserve": minor_to_money(r["reinsurer_reserve_share"], canonical.currency),
            "CashPaid": minor_to_money(0, canonical.currency),
            "ReinstatementPremiumDue": minor_to_money(0, canonical.currency),
            "ProofVerification": r["invariant_status"],
        }
    if result["verdict"] == "Covered":
        s = result["settlement"]
        body["FinancialSummary"] = {
            "CurrencyCode": canonical.currency,
            "Layer100PctCeded": minor_to_money(s["ceded100"], canonical.currency),
            "ReinsurerNetCededShare": minor_to_money(s["reinsurerCeded"], canonical.currency),
            "ReinsurerReinstatementPremium": minor_to_money(s["reinsurerPremium"], canonical.currency),
            "RemainingAggregateLimit": minor_to_money(s["remainingAggregate"], canonical.currency),
            "ProofVerification": s["invariant"],
        }
    return body
