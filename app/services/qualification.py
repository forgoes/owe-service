from __future__ import annotations

from app.schemas.chat import (
    BusinessSegment,
    ContractStatus,
    LeadBucket,
    LeadProfile,
    QualificationResult,
    QualificationTier,
)


def estimate_usage_mwh(profile: LeadProfile, commercial_rate: float, industrial_rate: float) -> float | None:
    if profile.square_footage is None or profile.business_segment is None:
        return None

    multiplier = (
        industrial_rate
        if profile.business_segment == BusinessSegment.INDUSTRIAL
        else commercial_rate
    )
    return round(profile.square_footage * multiplier, 2)


def should_ask_building_age(profile: LeadProfile) -> bool:
    if profile.business_segment == BusinessSegment.INDUSTRIAL:
        return (
            profile.annual_usage_mwh is not None
            and 100 <= profile.annual_usage_mwh <= 500
            and profile.contract_expiry_months is not None
            and profile.contract_expiry_months < 12
        )

    if profile.business_segment == BusinessSegment.COMMERCIAL:
        return (
            profile.annual_usage_mwh is not None
            and 20 <= profile.annual_usage_mwh <= 50
            and profile.contract_status == ContractStatus.FIXED_TERM
        )

    return False


def missing_fields(profile: LeadProfile) -> list[str]:
    fields: list[str] = []

    if profile.contract_status == ContractStatus.NO_CURRENT_PROVIDER:
        if profile.business_segment is None:
            fields.append("business_segment")
        return fields

    if profile.business_segment is None:
        fields.append("business_segment")

    if profile.contract_status == ContractStatus.UNKNOWN:
        fields.append("contract_status")

    if (
        profile.contract_status in {ContractStatus.EXPIRING, ContractStatus.FIXED_TERM}
        and profile.contract_expiry_months is None
    ):
        fields.append("contract_expiry_months")

    if profile.annual_usage_mwh is None and profile.square_footage is None:
        fields.append("annual_usage_or_square_footage")

    if should_ask_building_age(profile) and profile.building_age_years is None:
        fields.append("building_age_years")

    return fields


def qualify_lead(profile: LeadProfile) -> QualificationResult:
    if profile.contract_status == ContractStatus.NO_CURRENT_PROVIDER:
        return QualificationResult(
            tier=QualificationTier.TIER_1,
            bucket=LeadBucket.GOLD,
            reasoning="No current energy provider is an instant-priority scenario.",
        )

    if (
        profile.business_segment == BusinessSegment.INDUSTRIAL
        and profile.annual_usage_mwh is not None
        and profile.annual_usage_mwh > 500
        and profile.contract_expiry_months is not None
        and profile.contract_expiry_months < 6
    ):
        return QualificationResult(
            tier=QualificationTier.TIER_1,
            bucket=LeadBucket.GOLD,
            reasoning="Industrial account above 500 MWh with a contract expiring in under 6 months.",
        )

    if (
        profile.business_segment == BusinessSegment.INDUSTRIAL
        and profile.annual_usage_mwh is not None
        and 100 <= profile.annual_usage_mwh <= 500
        and profile.contract_expiry_months is not None
        and profile.contract_expiry_months < 12
        and profile.building_age_years is not None
        and profile.building_age_years < 5
    ):
        return QualificationResult(
            tier=QualificationTier.TIER_2,
            bucket=LeadBucket.WARM,
            reasoning="Industrial account in the 100-500 MWh band with a near-term renewal and a newer facility.",
        )

    if (
        profile.business_segment == BusinessSegment.COMMERCIAL
        and profile.annual_usage_mwh is not None
        and profile.annual_usage_mwh > 50
        and profile.contract_status == ContractStatus.MONTH_TO_MONTH
    ):
        return QualificationResult(
            tier=QualificationTier.TIER_1,
            bucket=LeadBucket.GOLD,
            reasoning="Commercial account above 50 MWh on a month-to-month agreement.",
        )

    if (
        profile.business_segment == BusinessSegment.COMMERCIAL
        and profile.annual_usage_mwh is not None
        and 20 <= profile.annual_usage_mwh <= 50
        and profile.contract_status == ContractStatus.FIXED_TERM
        and profile.building_age_years is not None
        and profile.building_age_years < 2
    ):
        return QualificationResult(
            tier=QualificationTier.TIER_3,
            bucket=LeadBucket.WARM,
            reasoning="Commercial account in the 20-50 MWh band on fixed term with a very new building.",
        )

    return QualificationResult(
        tier=QualificationTier.UNQUALIFIED,
        bucket=LeadBucket.LEMON,
        reasoning="The current profile does not yet match any priority tier in the qualification matrix.",
    )
