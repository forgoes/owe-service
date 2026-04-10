from __future__ import annotations

import time
import re

from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

from app.runtime.observability import langsmith_config
from app.schemas.chat import BusinessSegment, ContractStatus, LeadProfile
from app.services.intent_classifier import is_transient_llm_error
from app.services.langchain_runtime import get_chat_model


class ProfileExtraction(BaseModel):
    business_segment: BusinessSegment | None = None
    annual_usage_mwh: float | None = None
    square_footage: int | None = None
    contract_status: ContractStatus | None = None
    contract_expiry_months: int | None = None
    building_age_years: int | None = None
    has_current_provider: bool | None = None


class ProfileExtractor:
    @property
    def _extractor(self):
        return get_chat_model(temperature=0.0).with_structured_output(
            ProfileExtraction
        )

    def extract(
        self,
        message: str,
        existing_profile: LeadProfile,
        language: str,
    ) -> ProfileExtraction:
        extractor = self._extractor

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Extract only explicitly supported business energy intake fields from the user's latest message. "
                    "Return null for fields that are not clearly stated. "
                    "Map no current provider to contract_status=no_current_provider and has_current_provider=false. "
                    "Map month-to-month, fixed term, expiring, commercial, industrial, usage in MWh, "
                    "square footage, building age in years, and contract expiry months when present. "
                    "The user may speak any language.",
                ),
                (
                    "human",
                    "Language: {language}\nExisting profile: {profile}\nLatest message: {message}",
                ),
            ]
        )

        chain = prompt | extractor
        payload = {
            "language": language,
            "profile": existing_profile.model_dump_json(),
            "message": message,
        }
        config = langsmith_config(
            "profile_extractor",
            tags=["qualification", "extraction"],
            metadata={"language": language},
        )
        for attempt in range(3):
            try:
                return chain.invoke(payload, config=config)
            except Exception as exc:
                if not is_transient_llm_error(exc) or attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))

    def _extract_int(self, pattern: str, text: str) -> int | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))

    def _extract_float(self, pattern: str, text: str) -> float | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        return float(match.group(1).replace(",", ""))


profile_extractor = ProfileExtractor()
