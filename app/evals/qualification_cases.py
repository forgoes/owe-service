from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chat import QualificationTier


@dataclass(frozen=True)
class QualificationEvalCase:
    name: str
    message: str
    expected_tier: QualificationTier
    expected_missing_fields: tuple[str, ...] = ()


CASES: tuple[QualificationEvalCase, ...] = (
    QualificationEvalCase(
        name="industrial_instant_priority",
        message="We operate an industrial facility using 620 MWh and the contract expires in 4 months.",
        expected_tier=QualificationTier.TIER_1,
    ),
    QualificationEvalCase(
        name="industrial_follow_up_needs_building_age",
        message="This is an industrial site using 320 MWh and the contract expires in 8 months.",
        expected_tier=QualificationTier.UNQUALIFIED,
        expected_missing_fields=("building_age_years",),
    ),
    QualificationEvalCase(
        name="commercial_month_to_month_priority",
        message="We are a commercial site on a month-to-month contract using 80 MWh.",
        expected_tier=QualificationTier.TIER_1,
    ),
    QualificationEvalCase(
        name="commercial_nurture_tier_three",
        message="We are a commercial site using 35 MWh on a fixed term contract and the building is 1 year old.",
        expected_tier=QualificationTier.TIER_3,
    ),
    QualificationEvalCase(
        name="no_provider_priority",
        message="We are an industrial customer and we do not have a current provider.",
        expected_tier=QualificationTier.TIER_1,
    ),
    QualificationEvalCase(
        name="industrial_no_provider_priority",
        message="We are an industrial customer and currently have no provider.",
        expected_tier=QualificationTier.TIER_1,
    ),
    QualificationEvalCase(
        name="square_footage_fallback",
        message="We are a commercial site on a month-to-month contract with 40000 square feet.",
        expected_tier=QualificationTier.TIER_1,
    ),
)
