from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class BusinessSegment(str, Enum):
    INDUSTRIAL = "industrial"
    COMMERCIAL = "commercial"


class ContractStatus(str, Enum):
    UNKNOWN = "unknown"
    EXPIRING = "expiring"
    MONTH_TO_MONTH = "month_to_month"
    FIXED_TERM = "fixed_term"
    NO_CURRENT_PROVIDER = "no_current_provider"


class QualificationTier(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    UNQUALIFIED = "unqualified"


class LeadBucket(str, Enum):
    GOLD = "gold"
    WARM = "warm"
    LEMON = "lemon"


class ConversationMode(str, Enum):
    GENERAL = "general"
    QUALIFICATION = "qualification"


class IntentType(str, Enum):
    GENERAL_CHAT = "general_chat"
    PRODUCT_QUESTION = "product_question"
    BUSINESS_QUALIFICATION = "business_qualification"
    BUSINESS_CLARIFICATION = "business_clarification"
    OFF_TOPIC = "off_topic"


class ReplyMode(str, Enum):
    GENERAL = "general"
    PRODUCT = "product"
    QUALIFICATION = "qualification"
    CLARIFICATION = "clarification"
    REDIRECT = "redirect"
    ERROR = "error"

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class LeadProfile(BaseModel):
    business_segment: BusinessSegment | None = None
    annual_usage_mwh: float | None = None
    usage_estimated: bool = False
    square_footage: int | None = None
    contract_status: ContractStatus = ContractStatus.UNKNOWN
    contract_expiry_months: int | None = None
    building_age_years: int | None = None
    has_current_provider: bool | None = None
    notes: list[str] = Field(default_factory=list)


class QualificationResult(BaseModel):
    tier: QualificationTier = QualificationTier.UNQUALIFIED
    bucket: LeadBucket = LeadBucket.LEMON
    reasoning: str


class ConversationState(BaseModel):
    session_id: str
    mode: ConversationMode = ConversationMode.GENERAL
    detected_language: str = "en"
    profile: LeadProfile
    qualification: QualificationResult
    missing_fields: list[str] = Field(default_factory=list)
    next_question: str
    completed: bool = False
    last_intent: IntentType | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[Message] | None = None
    profile: LeadProfile | None = None


class ChatResponseSnapshot(BaseModel):
    assistant_message: str
    state: ConversationState


class OrchestrationOutcome(BaseModel):
    assistant_message: str
    state: ConversationState
    reply_mode: ReplyMode = ReplyMode.QUALIFICATION


class ConversationSession(BaseModel):
    state: ConversationState
    messages: list[Message] = Field(default_factory=list)
