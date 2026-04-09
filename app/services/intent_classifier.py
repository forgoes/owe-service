from __future__ import annotations

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError, field_validator

from app.runtime.observability import langsmith_config
from app.schemas.chat import ConversationMode, IntentType
from app.services.language import normalize_language_code
from app.services.langchain_runtime import get_chat_model


class IntentClassification(BaseModel):
    intent: IntentType
    language: str

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_code(value)


class IntentClassifier:
    @property
    def _classifier(self):
        return get_chat_model(temperature=0.0).with_structured_output(
            IntentClassification
        )

    def classify(
        self,
        message: str,
        mode: ConversationMode,
        existing_language: str | None = None,
    ) -> IntentClassification:
        classifier = self._classifier

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Classify the user's latest message for an energy lead qualification assistant. "
                        "intent must be one of: general_chat, product_question, business_qualification, "
                        "business_clarification, off_topic. "
                        "language must be a normalized lowercase language code such as en, zh, es, fr, or pt. "
                        "Use product_question when the user asks what this product/system/assistant does, "
                        "what it is for, what it can help with, how it works at a high level, "
                        "how to use it, how to ask better questions, what to ask first, or how to get started. "
                        "Use business_qualification when the user is discussing an energy lead, "
                        "contract, usage, provider, facility, commercial, industrial, square footage, "
                        "or qualification details. "
                        "If the user asks what one of those business terms means during qualification, "
                        "use business_clarification. "
                        "Questions like 'How should I ask?', 'What should I tell you?', "
                        "'How do I use this?', 'How should I get started?', "
                        "or questions asking how to phrase requests or how to get started "
                        "should usually be product_question, not general_chat. "
                        "Current confirmed language is {existing_language}. Keep that language unless the "
                        "latest user message clearly switches languages or explicitly asks you to reply "
                        "in another language. Do not switch languages just because the user pasted or quoted "
                        "text in a different language."
                    ),
                ),
                (
                    "human",
                    "Current mode: {mode}\nCurrent confirmed language: {existing_language}\n"
                    "Latest message: {message}",
                ),
            ]
        )

        return (prompt | classifier).invoke(
            {
                "mode": mode.value,
                "message": message,
                "existing_language": existing_language or "unknown",
            },
            config=langsmith_config(
                "intent_classifier",
                tags=["intent", "router"],
                metadata={
                    "mode": mode.value,
                    "existing_language": existing_language,
                },
            ),
        )


intent_classifier = IntentClassifier()


def is_transient_llm_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            APITimeoutError,
            APIConnectionError,
            InternalServerError,
            RateLimitError,
            OutputParserException,
            ValidationError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.TransportError,
        ),
    ):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {408, 409, 429} or exc.status_code >= 500
    if isinstance(exc, APIError):
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code in {408, 409, 429} or status_code >= 500
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 429} or exc.response.status_code >= 500
    return False
