from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from pydantic import BaseModel

from app.runtime.observability import langsmith_config
from app.schemas.chat import (
    ChatRequest,
    ConversationMode,
    ConversationState,
    IntentType,
    LeadBucket,
    LeadProfile,
    OrchestrationOutcome,
    QualificationResult,
    QualificationTier,
    ReplyMode,
)
from app.services.language import DEFAULT_LANGUAGE
from app.services.intent_classifier import intent_classifier, is_transient_llm_error
from app.services.orchestrator import build_qualification_outcome, merge_profile


class GraphState(BaseModel):
    request: ChatRequest | None = None
    previous_state: ConversationState | None = None
    routing_status: Literal["ready", "error"] | None = None
    intent: IntentType | None = None
    language: str | None = None
    merged_profile: LeadProfile | None = None
    response_prefix: str = ""
    current_state: ConversationState | None = None
    draft_message: str = ""
    reply_mode: ReplyMode | None = None
    outcome: OrchestrationOutcome | None = None


def _state_context(state: GraphState) -> tuple[ChatRequest, ConversationState, str]:
    request = state.request
    assert request is not None
    previous_state = state.previous_state or make_initial_state(request.session_id)
    language = state.language or previous_state.detected_language
    return request, previous_state, language


def _updated_state(
    request: ChatRequest,
    previous_state: ConversationState,
    language: str,
    *,
    mode: ConversationMode,
    last_intent: IntentType,
) -> ConversationState:
    return previous_state.model_copy(
        update={
            "session_id": request.session_id,
            "mode": mode,
            "detected_language": language,
            "last_intent": last_intent,
        }
    )


def make_initial_state(session_id: str) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        mode=ConversationMode.GENERAL,
        detected_language=DEFAULT_LANGUAGE,
        profile=LeadProfile(),
        qualification=QualificationResult(
            tier=QualificationTier.UNQUALIFIED,
            bucket=LeadBucket.LEMON,
            reasoning="No lead has been qualified yet.",
        ),
        missing_fields=[],
        next_question="Please share your business type, contract situation, energy usage, or building size to get started.",
        completed=False,
        last_intent=None,
    )


def route_llm_node(state: GraphState) -> dict[str, Any]:
    request = state.request
    previous_state = state.previous_state
    assert request is not None

    mode = previous_state.mode if previous_state else ConversationMode.GENERAL
    existing_language = previous_state.detected_language if previous_state else None
    if previous_state is not None:
        slot_fill_result = _route_by_slot_fill(
            request=request,
            previous_state=previous_state,
            language=existing_language or DEFAULT_LANGUAGE,
        )
        if slot_fill_result is not None:
            return slot_fill_result
    try:
        result = intent_classifier.classify(
            request.message,
            mode,
            existing_language,
        )
    except Exception as exc:
        if is_transient_llm_error(exc):
            raise
        return {"routing_status": "error"}

    return {
        "routing_status": "ready",
        "intent": result.intent,
        "language": result.language,
    }


def route_error_node(state: GraphState) -> dict[str, Any]:
    request = state.request
    previous_state = state.previous_state
    assert request is not None

    current_state = previous_state or make_initial_state(request.session_id)
    return {
        "routing_status": "ready",
        "current_state": current_state,
        "draft_message": (
            "I couldn't process your last message reliably just now. "
            "Please try sending it again in a moment."
        ),
        "reply_mode": ReplyMode.ERROR,
    }


def route_dispatch_node(_: GraphState) -> dict[str, Any]:
    return {}


def general_chat_node(state: GraphState) -> dict[str, Any]:
    request, previous_state, language = _state_context(state)
    updated_state = _updated_state(
        request,
        previous_state,
        language,
        mode=ConversationMode.GENERAL,
        last_intent=IntentType.GENERAL_CHAT,
    )
    return {
        "current_state": updated_state,
        "draft_message": (
            "Reply as a focused business energy information intake assistant. "
            "For greetings or vague openers, briefly explain that you help collect the business details needed for an energy consultation and follow-up. "
            "Invite the user to share business type, contract status, usage, provider status, or building size. "
            "Do not present yourself as a general-purpose chat assistant or as a lead-scoring tool."
        ),
        "reply_mode": ReplyMode.GENERAL,
    }


def product_question_node(state: GraphState) -> dict[str, Any]:
    request, previous_state, language = _state_context(state)
    updated_state = _updated_state(
        request,
        previous_state,
        language,
        mode=ConversationMode.GENERAL,
        last_intent=IntentType.PRODUCT_QUESTION,
    )
    draft_message = (
        "Introduce this product as a business energy intake assistant for commercial and industrial customers. "
        "Explain that it helps collect the details our team needs, such as business type, usage, contract timing, provider status, and facility information. "
        "If the user is asking how to use it or what to ask, give a few concrete example prompts such as "
        "'We run a hotel using about 120 MWh and the contract expires in 4 months', "
        "'We do not currently have an energy supplier', or "
        "'Our restaurant has 40,000 square feet and a fixed-term contract'. "
        "Mention that the user can start from just one known detail and the system will guide them through the rest."
    )
    return {
        "current_state": updated_state,
        "draft_message": draft_message,
        "reply_mode": ReplyMode.PRODUCT,
    }


def extract_profile_node(state: GraphState) -> dict[str, Any]:
    request = state.request
    previous_state = state.previous_state
    assert request is not None
    language = state.language or (
        previous_state.detected_language if previous_state else DEFAULT_LANGUAGE
    )
    base_profile = previous_state.profile if previous_state else (request.profile or LeadProfile())
    merged_profile = state.merged_profile or merge_profile(base_profile, request.message, language)
    response_prefix = ""
    if (
        previous_state is not None
        and previous_state.profile.annual_usage_mwh is None
        and merged_profile.usage_estimated
        and merged_profile.square_footage is not None
    ):
        response_prefix = (
            f"I estimated annual usage at about {merged_profile.annual_usage_mwh} MWh from "
            f"{merged_profile.square_footage:,} square feet. "
        )
    return {
        "language": language,
        "merged_profile": merged_profile,
        "response_prefix": response_prefix,
    }


def _route_by_slot_fill(
    request: ChatRequest,
    previous_state: ConversationState,
    language: str,
) -> dict[str, Any] | None:
    if previous_state.mode != ConversationMode.QUALIFICATION:
        return None
    if not previous_state.missing_fields:
        return None

    try:
        merged_profile = merge_profile(previous_state.profile, request.message, language)
    except Exception:
        return None

    if not _fills_any_missing_field(
        previous_state.profile,
        merged_profile,
        previous_state.missing_fields,
    ):
        return None

    return {
        "routing_status": "ready",
        "intent": IntentType.BUSINESS_QUALIFICATION,
        "language": language,
        "merged_profile": merged_profile,
    }


def _fills_any_missing_field(
    previous_profile: LeadProfile,
    merged_profile: LeadProfile,
    missing_fields: list[str],
) -> bool:
    for field in missing_fields:
        if field == "business_segment" and (
            merged_profile.business_segment is not None
            and merged_profile.business_segment != previous_profile.business_segment
        ):
            return True

        if field == "contract_status" and (
            merged_profile.contract_status != previous_profile.contract_status
            and merged_profile.contract_status.value != "unknown"
        ):
            return True

        if field == "contract_expiry_months" and (
            merged_profile.contract_expiry_months is not None
            and merged_profile.contract_expiry_months != previous_profile.contract_expiry_months
        ):
            return True

        if field == "annual_usage_or_square_footage":
            if (
                merged_profile.annual_usage_mwh is not None
                and merged_profile.annual_usage_mwh != previous_profile.annual_usage_mwh
            ):
                return True
            if (
                merged_profile.square_footage is not None
                and merged_profile.square_footage != previous_profile.square_footage
            ):
                return True

        if field == "building_age_years" and (
            merged_profile.building_age_years is not None
            and merged_profile.building_age_years != previous_profile.building_age_years
        ):
            return True

    return False


def evaluate_qualification_node(state: GraphState) -> dict[str, Any]:
    request = state.request
    previous_state = state.previous_state
    assert request is not None
    language = state.language or (
        previous_state.detected_language if previous_state else DEFAULT_LANGUAGE
    )
    merged_profile = state.merged_profile
    assert merged_profile is not None
    qualification_outcome = build_qualification_outcome(
        request=request,
        previous_state=previous_state,
        merged_profile=merged_profile,
        language=language,
    )

    prefix = state.response_prefix
    draft_message = qualification_outcome.assistant_message
    if prefix and not qualification_outcome.state.completed:
        draft_message = f"{prefix}{draft_message}"
    return {
        "current_state": qualification_outcome.state,
        "draft_message": draft_message,
        "reply_mode": ReplyMode.QUALIFICATION,
    }


def clarification_node(state: GraphState) -> dict[str, Any]:
    request, previous_state, language = _state_context(state)
    updated_state = _updated_state(
        request,
        previous_state,
        language,
        mode=ConversationMode.QUALIFICATION,
        last_intent=IntentType.BUSINESS_CLARIFICATION,
    )
    return {
        "current_state": updated_state,
        "draft_message": f"Sure. {updated_state.next_question}",
        "reply_mode": ReplyMode.CLARIFICATION,
    }


def redirect_node(state: GraphState) -> dict[str, Any]:
    request, previous_state, language = _state_context(state)
    updated_state = _updated_state(
        request,
        previous_state,
        language,
        mode=ConversationMode.QUALIFICATION,
        last_intent=IntentType.OFF_TOPIC,
    )
    return {
        "current_state": updated_state,
        "draft_message": f"Happy to help briefly. After that, {updated_state.next_question}",
        "reply_mode": ReplyMode.REDIRECT,
    }


def compose_response_node(state: GraphState) -> dict[str, Any]:
    assert state.current_state is not None
    assert state.reply_mode is not None
    return {
        "outcome": OrchestrationOutcome(
            assistant_message=state.draft_message,
            state=state.current_state,
            reply_mode=state.reply_mode,
        )
    }


def select_route_target(
    state: GraphState,
) -> Literal["general", "product", "extract_profile", "clarification", "redirect"]:
    intent = state.intent
    if intent == IntentType.PRODUCT_QUESTION:
        return "product"
    if intent == IntentType.BUSINESS_QUALIFICATION:
        return "extract_profile"
    if intent == IntentType.BUSINESS_CLARIFICATION:
        return "clarification"
    if intent == IntentType.OFF_TOPIC:
        return "redirect"
    return "general"


def select_routing_strategy(state: GraphState) -> Literal["dispatch", "error"]:
    if state.routing_status == "error":
        return "error"
    return "dispatch"


graph_builder = StateGraph(GraphState)
graph_builder.add_node(
    "route_llm",
    route_llm_node,
    retry_policy=RetryPolicy(max_attempts=3, retry_on=is_transient_llm_error),
)
graph_builder.add_node("route_error", route_error_node)
graph_builder.add_node("route_dispatch", route_dispatch_node)
graph_builder.add_node("general", general_chat_node)
graph_builder.add_node("product", product_question_node)
graph_builder.add_node("extract_profile", extract_profile_node)
graph_builder.add_node("evaluate_qualification", evaluate_qualification_node)
graph_builder.add_node("clarification", clarification_node)
graph_builder.add_node("redirect", redirect_node)
graph_builder.add_node("compose_response", compose_response_node)
graph_builder.add_edge(START, "route_llm")
graph_builder.add_conditional_edges(
    "route_llm",
    select_routing_strategy,
    {
        "dispatch": "route_dispatch",
        "error": "route_error",
    },
)
graph_builder.add_conditional_edges(
    "route_dispatch",
    select_route_target,
    {
        "general": "general",
        "product": "product",
        "extract_profile": "extract_profile",
        "clarification": "clarification",
        "redirect": "redirect",
    },
)
graph_builder.add_edge("extract_profile", "evaluate_qualification")
graph_builder.add_edge("route_error", "compose_response")
graph_builder.add_edge("general", "compose_response")
graph_builder.add_edge("product", "compose_response")
graph_builder.add_edge("evaluate_qualification", "compose_response")
graph_builder.add_edge("clarification", "compose_response")
graph_builder.add_edge("redirect", "compose_response")
graph_builder.add_edge("compose_response", END)

lead_agent_graph = graph_builder.compile()


def run_lead_agent(
    request: ChatRequest,
    previous_state: ConversationState | None,
) -> OrchestrationOutcome:
    initial_state = GraphState(
        request=request,
        previous_state=previous_state,
    )
    config = langsmith_config(
        "lead_agent_graph",
        tags=["langgraph", "lead-qualification"],
        metadata={
            "session_id": request.session_id,
            "has_previous_state": previous_state is not None,
            "existing_mode": previous_state.mode.value if previous_state else "general",
            "existing_language": (
                previous_state.detected_language if previous_state else DEFAULT_LANGUAGE
            ),
        },
    )
    try:
        result = lead_agent_graph.invoke(initial_state, config=config)
    except Exception as exc:
        if not is_transient_llm_error(exc):
            raise
        error_state = previous_state or make_initial_state(request.session_id)
        return OrchestrationOutcome(
            assistant_message=(
                "I couldn't process your last message reliably just now. "
                "Please try sending it again in a moment."
            ),
            state=error_state,
            reply_mode=ReplyMode.ERROR,
        )
    outcome = result["outcome"] if isinstance(result, dict) else result.outcome
    return outcome
