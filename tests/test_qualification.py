from app.evals.qualification_cases import CASES
from app.schemas.chat import (
    BusinessSegment,
    ChatRequest,
    ContractStatus,
    LeadProfile,
    QualificationTier,
)
from app.services.graph import run_lead_agent
from app.services.orchestrator import merge_profile
from app.services.qualification import missing_fields, qualify_lead


def test_no_provider_is_tier_one() -> None:
    profile = LeadProfile(contract_status=ContractStatus.NO_CURRENT_PROVIDER)
    result = qualify_lead(profile)
    assert result.tier == QualificationTier.TIER_1


def test_industrial_follow_up_requires_building_age() -> None:
    profile = LeadProfile(
        business_segment=BusinessSegment.INDUSTRIAL,
        annual_usage_mwh=320,
        contract_status=ContractStatus.EXPIRING,
        contract_expiry_months=8,
    )
    assert "building_age_years" in missing_fields(profile)


def test_merge_profile_extracts_english_fields() -> None:
    profile = merge_profile(
        LeadProfile(),
        "We are an industrial customer with no current provider and 20,000 square feet.",
        "en",
    )

    assert profile.business_segment == BusinessSegment.INDUSTRIAL
    assert profile.contract_status == ContractStatus.NO_CURRENT_PROVIDER
    assert profile.square_footage == 20000


def test_langgraph_qualification_flow_builds_state() -> None:
    outcome = run_lead_agent(
        ChatRequest(
            session_id="test-session",
            message="We are a commercial site on a month-to-month contract using 80 MWh.",
        ),
        previous_state=None,
    )

    assert outcome.reply_mode.value == "qualification"
    assert outcome.state.profile.business_segment == BusinessSegment.COMMERCIAL
    assert outcome.state.profile.contract_status == ContractStatus.MONTH_TO_MONTH
    assert outcome.state.qualification.tier == QualificationTier.TIER_1


def test_product_question_routes_to_product_mode_reply() -> None:
    outcome = run_lead_agent(
        ChatRequest(
            session_id="product-question",
            message="What kind of product is this?",
        ),
        previous_state=None,
    )

    assert outcome.reply_mode.value == "product"
    assert outcome.state.last_intent is not None
    assert outcome.state.last_intent.value == "product_question"
    assert outcome.state.mode.value == "general"


def test_eval_cases_match_expected_tiers() -> None:
    for index, case in enumerate(CASES, start=1):
        outcome = run_lead_agent(
            ChatRequest(
                session_id=f"pytest-eval-{index}",
                message=case.message,
            ),
            previous_state=None,
        )

        assert outcome.state.qualification.tier == case.expected_tier
        if case.expected_missing_fields:
            assert tuple(outcome.state.missing_fields) == case.expected_missing_fields
