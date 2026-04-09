from __future__ import annotations

import re

from app.runtime.config import settings
from app.schemas.chat import (
    BusinessSegment,
    ChatRequest,
    ChatResponseSnapshot,
    ConversationMode,
    ContractStatus,
    ConversationState,
    IntentType,
    LeadProfile,
    OrchestrationOutcome,
    ReplyMode,
)
from app.services.language import DEFAULT_LANGUAGE
from app.services.profile_extractor import profile_extractor
from app.services.qualification import estimate_usage_mwh, missing_fields, qualify_lead


def _extract_number(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def merge_profile(
    existing: LeadProfile,
    user_message: str,
    language: str,
) -> LeadProfile:
    lowered = user_message.lower()
    profile = existing.model_copy(deep=True)
    extracted = profile_extractor.extract(
        message=user_message,
        existing_profile=existing,
        language=language,
    )

    if extracted.business_segment is not None:
        profile.business_segment = extracted.business_segment
    if extracted.contract_status is not None:
        profile.contract_status = extracted.contract_status
    if extracted.has_current_provider is not None:
        profile.has_current_provider = extracted.has_current_provider
    if extracted.annual_usage_mwh is not None:
        profile.annual_usage_mwh = extracted.annual_usage_mwh
        profile.usage_estimated = False
    if extracted.square_footage is not None:
        profile.square_footage = extracted.square_footage
    if extracted.building_age_years is not None:
        profile.building_age_years = extracted.building_age_years
    if extracted.contract_expiry_months is not None:
        profile.contract_expiry_months = extracted.contract_expiry_months

    if "industrial" in lowered:
        profile.business_segment = BusinessSegment.INDUSTRIAL
    elif "commercial" in lowered:
        profile.business_segment = BusinessSegment.COMMERCIAL

    if (
        "no current provider" in lowered
        or "no provider" in lowered
        or "do not have a current provider" in lowered
        or "don't have a current provider" in lowered
        or "dont have a current provider" in lowered
    ):
        profile.contract_status = ContractStatus.NO_CURRENT_PROVIDER
        profile.has_current_provider = False
    elif "month-to-month" in lowered or "month to month" in lowered:
        profile.contract_status = ContractStatus.MONTH_TO_MONTH
        profile.has_current_provider = True
    elif "fixed" in lowered and "term" in lowered:
        profile.contract_status = ContractStatus.FIXED_TERM
        profile.has_current_provider = True
    elif "expiring" in lowered or "expires" in lowered or "renewal" in lowered:
        profile.contract_status = ContractStatus.EXPIRING
        profile.has_current_provider = True

    annual_usage = _extract_float(r"(\d+(?:,\d+)?(?:\.\d+)?)\s*mwh", user_message)
    if annual_usage is not None:
        profile.annual_usage_mwh = annual_usage
        profile.usage_estimated = False

    square_footage = _extract_number(r"(\d[\d,]*)\s*(?:sq\s*ft|sqft|square feet)", user_message)
    if square_footage is not None:
        profile.square_footage = square_footage

    building_age = _extract_number(r"(\d+)\s*(?:years old|year old|yrs old|yrs|years)", user_message)
    if building_age is not None:
        profile.building_age_years = building_age

    expiry_months = _extract_number(r"(\d+)\s*(?:months|month)", user_message)
    if expiry_months is not None and profile.contract_status in {
        ContractStatus.EXPIRING,
        ContractStatus.FIXED_TERM,
    }:
        profile.contract_expiry_months = expiry_months

    if profile.annual_usage_mwh is None and profile.square_footage is not None:
        estimated = estimate_usage_mwh(
            profile,
            commercial_rate=settings.estimated_mwh_per_sqft_commercial,
            industrial_rate=settings.estimated_mwh_per_sqft_industrial,
        )
        if estimated is not None:
            profile.annual_usage_mwh = estimated
            profile.usage_estimated = True

    return profile


def determine_next_question(
    profile: LeadProfile,
    fields: list[str],
) -> str:
    if profile.contract_status == ContractStatus.NO_CURRENT_PROVIDER:
        if "business_segment" in fields:
            return "Before I finalize it, is this lead commercial or industrial?"
        return "Thanks. I have enough information to mark this as an instant-priority lead."

    if "business_segment" in fields:
        return "Are you qualifying a commercial site or an industrial facility?"
    if "contract_status" in fields:
        return "What is your current contract situation: expiring soon, fixed term, month-to-month, or no current provider?"
    if "contract_expiry_months" in fields:
        return "How many months remain on the current energy contract?"
    if "annual_usage_or_square_footage" in fields:
        return "Do you know the annual electricity usage in MWh? If not, share the building square footage and I can estimate it."
    if "building_age_years" in fields:
        return "How old is the building or facility in years?"
    if profile.annual_usage_mwh is not None:
        return "I have enough information to evaluate this lead. Want a concise qualification summary?"
    return "Tell me a bit more about the site so I can complete the qualification matrix."


def build_state_from_profile(
    session_id: str,
    profile: LeadProfile,
    language: str,
) -> ConversationState:
    required_fields = missing_fields(profile)
    qualification = qualify_lead(profile)
    completed = len(required_fields) == 0
    next_question = determine_next_question(profile, required_fields)

    return ConversationState(
        session_id=session_id,
        mode=ConversationMode.QUALIFICATION,
        detected_language=language,
        profile=profile,
        qualification=qualification,
        missing_fields=required_fields,
        next_question=next_question,
        completed=completed,
        last_intent=IntentType.BUSINESS_QUALIFICATION,
    )


def build_clarification_message(
    user_message: str,
    previous_state: ConversationState | None,
    current_state: ConversationState,
) -> str | None:
    if previous_state is None:
        return None

    normalized = user_message.strip().lower()
    if not normalized:
        return None

    ambiguous_replies = {
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "hello",
        "hi",
        "hey",
    }

    if normalized not in ambiguous_replies:
        return None

    if (
        "business_segment" in current_state.missing_fields
        and "business_segment" in previous_state.missing_fields
    ):
        return "I still need the business type to continue. Please reply with either 'commercial' or 'industrial'."

    if (
        "contract_status" in current_state.missing_fields
        and "contract_status" in previous_state.missing_fields
    ):
        return "I still need the contract status. Please reply with one of: expiring, fixed term, month-to-month, or no current provider."

    if (
        "annual_usage_or_square_footage" in current_state.missing_fields
        and "annual_usage_or_square_footage" in previous_state.missing_fields
    ):
        return "I still need either annual usage or building size. Please share the annual usage in MWh, or the square footage so I can estimate it."

    if (
        "building_age_years" in current_state.missing_fields
        and "building_age_years" in previous_state.missing_fields
    ):
        return "I still need the building age in years to finish qualification."

    return None


def build_response_text(state: ConversationState) -> str:
    profile = state.profile

    if not state.completed:
        if profile.usage_estimated and profile.square_footage is not None:
            return (
                f"I estimated annual usage at about {profile.annual_usage_mwh} MWh from "
                f"{profile.square_footage:,} square feet. {state.next_question}"
            )
        return state.next_question

    usage_label = (
        f"{profile.annual_usage_mwh} MWh estimated from square footage"
        if profile.usage_estimated
        else f"{profile.annual_usage_mwh} MWh"
    )
    return (
        f"This lead is currently {state.qualification.tier.value.replace('_', ' ').upper()} "
        f"and maps to a {state.qualification.bucket.value.upper()} bucket. "
        f"Reason: {state.qualification.reasoning} "
        f"Captured profile: segment={profile.business_segment.value if profile.business_segment else 'unknown'}, "
        f"usage={usage_label}, contract={profile.contract_status.value}, "
        f"expiry_months={profile.contract_expiry_months}, building_age={profile.building_age_years}."
    )


def build_qualification_outcome(
    request: ChatRequest,
    previous_state: ConversationState | None,
    merged_profile: LeadProfile,
    language: str,
) -> OrchestrationOutcome:
    state = build_state_from_profile(
        session_id=request.session_id,
        profile=merged_profile,
        language=language,
    )
    assistant_message = (
        build_clarification_message(
            user_message=request.message,
            previous_state=previous_state,
            current_state=state,
        )
        or build_response_text(state)
    )
    return OrchestrationOutcome(
        assistant_message=assistant_message,
        state=state,
        reply_mode=ReplyMode.QUALIFICATION,
    )


def build_snapshot(
    request: ChatRequest,
    previous_state: ConversationState | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> ChatResponseSnapshot:
    base_profile = request.profile or LeadProfile()
    merged_profile = merge_profile(base_profile, request.message, language)
    outcome = build_qualification_outcome(
        request=request,
        previous_state=previous_state,
        merged_profile=merged_profile,
        language=language,
    )
    return ChatResponseSnapshot(
        assistant_message=outcome.assistant_message,
        state=outcome.state,
    )
