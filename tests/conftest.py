from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "langchain_openai" not in sys.modules:
    langchain_openai = types.ModuleType("langchain_openai")

    class ChatOpenAI:  # pragma: no cover - test import shim
        def __init__(self, *args, **kwargs) -> None:
            pass

    langchain_openai.ChatOpenAI = ChatOpenAI
    sys.modules["langchain_openai"] = langchain_openai

from app.schemas.chat import (
    BusinessSegment,
    ContractStatus,
    ConversationMode,
    IntentType,
)
from app.services.intent_classifier import IntentClassification, intent_classifier
from app.services.profile_extractor import ProfileExtraction, profile_extractor

CN_RESTAURANT = "\u9910\u5385"
CN_HOTEL = "\u9152\u5e97"
CN_WAREHOUSE = "\u4ed3\u5e93"
CN_FACTORY = "\u5de5\u5382"
CN_OFFICE = "\u529e\u516c\u5ba4"
CN_COMMERCIAL = "\u5546\u4e1a"
CN_INDUSTRIAL = "\u5de5\u4e1a"
CN_MONTH_TO_MONTH_1 = "\u6309\u6708\u7eed\u7ea6"
CN_MONTH_TO_MONTH_2 = "\u6708\u6708\u7eed\u7ea6"
CN_MONTH_TO_MONTH_3 = "\u6708\u5ea6\u7eed\u7ea6"
CN_FIXED_TERM_1 = "\u56fa\u5b9a\u5408\u540c"
CN_FIXED_TERM_2 = "\u56fa\u5b9a\u5408\u540c\u671f\u5185"
CN_FIXED_TERM_3 = "\u56fa\u5b9a\u671f\u9650\u5408\u540c"
CN_FIXED_TERM_4 = "\u56fa\u5b9a\u671f\u9650\u5185"
CN_EXPIRING_1 = "\u5feb\u5230\u671f"
CN_EXPIRING_2 = "\u5373\u5c06\u5230\u671f"
CN_EXPIRING_3 = "\u5feb\u7eed\u7ea6"
CN_EXPIRING_4 = "\u5373\u5c06\u7eed\u7ea6"
CN_NO_PROVIDER_1 = "\u6ca1\u6709\u4f9b\u5e94\u5546"
CN_NO_PROVIDER_2 = "\u6ca1\u6709\u80fd\u6e90\u4f9b\u5e94\u5546"
CN_NO_PROVIDER_3 = "\u76ee\u524d\u6ca1\u6709\u4f9b\u5e94\u5546"
CN_NO_PROVIDER_4 = "\u5f53\u524d\u6ca1\u6709\u4f9b\u5e94\u5546"


def _classify_for_tests(
    message: str,
    mode: ConversationMode,
    existing_language: str | None = None,
) -> IntentClassification:
    lowered = message.strip().lower()

    if any(
        phrase in lowered
        for phrase in (
            "what kind of product",
            "what is this product",
            "what is this",
            "how do i use this",
            "how should i ask",
            "how should i get started",
        )
    ):
        intent = IntentType.PRODUCT_QUESTION
    elif any(
        phrase in lowered
        for phrase in (
            "what do you mean",
            "what is month-to-month",
            "can you explain",
            "explain",
        )
    ):
        intent = (
            IntentType.BUSINESS_CLARIFICATION
            if mode == ConversationMode.QUALIFICATION
            else IntentType.GENERAL_CHAT
        )
    elif any(
        phrase in lowered
        for phrase in (
            "industrial",
            "commercial",
            "mwh",
            "contract",
            "provider",
            "renewal",
            "square feet",
            "sq ft",
            "facility",
            "building",
            "month-to-month",
            "fixed term",
            "expires",
            "expiring",
            CN_RESTAURANT,
            CN_HOTEL,
            CN_WAREHOUSE,
            CN_FACTORY,
            CN_OFFICE,
            CN_COMMERCIAL,
            CN_INDUSTRIAL,
            CN_MONTH_TO_MONTH_1,
            CN_MONTH_TO_MONTH_2,
            CN_MONTH_TO_MONTH_3,
            CN_FIXED_TERM_1,
            CN_FIXED_TERM_2,
            CN_FIXED_TERM_3,
            CN_FIXED_TERM_4,
            CN_EXPIRING_1,
            CN_EXPIRING_2,
            CN_EXPIRING_3,
            CN_EXPIRING_4,
            CN_NO_PROVIDER_1,
            CN_NO_PROVIDER_2,
            CN_NO_PROVIDER_3,
            CN_NO_PROVIDER_4,
        )
    ):
        intent = IntentType.BUSINESS_QUALIFICATION
    elif mode == ConversationMode.QUALIFICATION:
        intent = IntentType.OFF_TOPIC
    else:
        intent = IntentType.GENERAL_CHAT

    return IntentClassification(
        intent=intent,
        language=existing_language or "en",
    )


def _extract_for_tests(
    message: str,
    existing_profile,
    language: str,
) -> ProfileExtraction:
    lowered = message.lower()
    extraction = ProfileExtraction()

    if "industrial" in lowered:
        extraction.business_segment = BusinessSegment.INDUSTRIAL
    elif "commercial" in lowered:
        extraction.business_segment = BusinessSegment.COMMERCIAL

    if (
        "no current provider" in lowered
        or "no provider" in lowered
        or "do not have a current provider" in lowered
        or "don't have a current provider" in lowered
        or "dont have a current provider" in lowered
        or "currently have no provider" in lowered
        or CN_NO_PROVIDER_1 in message
        or CN_NO_PROVIDER_2 in message
        or CN_NO_PROVIDER_3 in message
        or CN_NO_PROVIDER_4 in message
    ):
        extraction.contract_status = ContractStatus.NO_CURRENT_PROVIDER
        extraction.has_current_provider = False
    elif (
        "month-to-month" in lowered
        or "month to month" in lowered
        or CN_MONTH_TO_MONTH_1 in message
        or CN_MONTH_TO_MONTH_2 in message
        or CN_MONTH_TO_MONTH_3 in message
    ):
        extraction.contract_status = ContractStatus.MONTH_TO_MONTH
        extraction.has_current_provider = True
    elif (
        ("fixed" in lowered and "term" in lowered)
        or CN_FIXED_TERM_1 in message
        or CN_FIXED_TERM_2 in message
        or CN_FIXED_TERM_3 in message
        or CN_FIXED_TERM_4 in message
    ):
        extraction.contract_status = ContractStatus.FIXED_TERM
        extraction.has_current_provider = True
    elif (
        "expiring" in lowered
        or "expires" in lowered
        or "renewal" in lowered
        or CN_EXPIRING_1 in message
        or CN_EXPIRING_2 in message
        or CN_EXPIRING_3 in message
        or CN_EXPIRING_4 in message
    ):
        extraction.contract_status = ContractStatus.EXPIRING
        extraction.has_current_provider = True

    import re

    annual_usage = re.search(r"(\d+(?:,\d+)?(?:\.\d+)?)\s*mwh", message, flags=re.IGNORECASE)
    if annual_usage:
        extraction.annual_usage_mwh = float(annual_usage.group(1).replace(",", ""))

    square_footage = re.search(
        r"(\d[\d,]*)\s*(?:sq\s*ft|sqft|square feet)",
        message,
        flags=re.IGNORECASE,
    )
    if square_footage:
        extraction.square_footage = int(square_footage.group(1).replace(",", ""))

    building_age = re.search(
        r"(\d+)\s*(?:years old|year old|yrs old|yrs|years)",
        message,
        flags=re.IGNORECASE,
    )
    if building_age:
        extraction.building_age_years = int(building_age.group(1))

    expiry_months = re.search(r"(\d+)\s*(?:months|month)", message, flags=re.IGNORECASE)
    if expiry_months:
        extraction.contract_expiry_months = int(expiry_months.group(1))

    return extraction


@pytest.fixture(autouse=True)
def stub_llm_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intent_classifier, "classify", _classify_for_tests)
    monkeypatch.setattr(profile_extractor, "extract", _extract_for_tests)
