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
        next_question="Start by telling me what you need help with.",
        completed=False,
        last_intent=None,
    )


def route_llm_node(state: GraphState) -> dict[str, Any]:
    request = state.request
    previous_state = state.previous_state
    assert request is not None

    mode = previous_state.mode if previous_state else ConversationMode.GENERAL
    existing_language = previous_state.detected_language if previous_state else None
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
            "Answer the user's question directly and naturally. "
            "If it is relevant, you may briefly mention that this system can also qualify energy sales leads, "
            "but do not force the conversation back to that workflow."
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
        "Introduce this product as an energy lead qualification assistant. "
        "Explain that it helps assess commercial and industrial energy opportunities by collecting details like usage, contract timing, provider status, and facility information. "
        "If the user is asking how to use it or what to ask, give a few concrete example prompts such as "
        "'This is a commercial site using 120 MWh with a contract expiring in 4 months', "
        "'We do not have a current provider', or "
        "'Can you help qualify this industrial facility lead?'. "
        "Mention that it can still start with a simple question and guide the user through the process."
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
    merged_profile = merge_profile(base_profile, request.message, language)
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
