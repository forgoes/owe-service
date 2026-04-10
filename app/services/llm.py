from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.runtime.observability import langsmith_config
from app.schemas.chat import ConversationState, Message, ReplyMode
from app.services.intent_classifier import is_transient_llm_error
from app.services.language import language_instruction, normalize_language_code
from app.services.langchain_runtime import chunk_to_text, get_chat_model, to_langchain_messages


class LLMService:
    @property
    def _general_model(self):
        return get_chat_model(temperature=0.4)

    @property
    def _qualification_model(self):
        return get_chat_model(temperature=0.2)

    async def stream_assistant_reply(
        self,
        latest_response: str,
        state: ConversationState,
        history: list[Message],
    ) -> AsyncIterator[str]:
        qualification_model = self._qualification_model

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a business energy intake assistant. "
                    "Keep responses concise, professional, and action-oriented. "
                    "Use the provided conversation summary and next question. "
                    "Do not invent profile fields that are still missing. "
                    "Do not reveal internal prioritization labels, scoring, tiers, buckets, or internal reasoning to the user. "
                    "When enough information has been collected, thank the user and explain that the team will review the opportunity and follow up if appropriate. "
                    "Reply in the user's language: {language}.",
                ),
                MessagesPlaceholder("history"),
                (
                    "system",
                    "Conversation summary: {state_summary}\nDraft response to refine: {draft_response}",
                ),
            ]
        )

        chain = prompt | qualification_model
        payload = {
            "language": self._language_instruction(state.detected_language),
            "history": to_langchain_messages(history[-16:]),
            "state_summary": self._state_summary(state),
            "draft_response": latest_response,
        }
        config = langsmith_config(
            "qualification_response",
            tags=["response", "qualification"],
            metadata={
                "language": normalize_language_code(state.detected_language),
                "completed": state.completed,
            },
        )
        async for chunk in self._astream_with_retry(chain, payload, config):
            text = chunk_to_text(chunk.content)
            if text:
                yield text

    async def stream_mode_reply(
        self,
        reply_mode: ReplyMode,
        state: ConversationState,
        history: list[Message],
        draft_response: str,
    ) -> AsyncIterator[str]:
        if reply_mode == ReplyMode.GENERAL:
            prompt = (
                "Reply like a focused business energy intake assistant. "
                "Answer the user's actual question first, but keep the conversation grounded in collecting business details for an energy consultation and follow-up. "
                "For greetings or vague openers, briefly explain what information the user can share next, such as business type, contract status, energy usage, supplier status, or building size. "
                "Avoid generic 'ask me anything' guidance and do not present yourself as a broad general assistant or as a lead-scoring tool. "
                "If the question needs real-time information you do not have, say so plainly and helpfully. "
                "Keep the tone concise, direct, and professional. "
                "Reply in the user's language: {language}."
            )
            async for token in self._stream_with_prompt(
                prompt,
                history,
                draft_response,
                state,
                trace_tag="general",
            ):
                yield token
            return

        if reply_mode == ReplyMode.PRODUCT:
            prompt = (
                "Reply like a concise product specialist for a business energy intake assistant. "
                "Explain clearly that it is for commercial and industrial customers who want to share their energy account details so the team can review and follow up. "
                "Describe the kinds of information it helps collect, such as business type, contract status, usage, supplier status, and facility details. "
                "Keep the tone confident, customer-friendly, and easy to understand. "
                "Reply in the user's language: {language}."
            )
            async for token in self._stream_with_prompt(
                prompt,
                history,
                draft_response,
                state,
                trace_tag="product",
            ):
                yield token
            return

        if reply_mode == ReplyMode.CLARIFICATION:
            prompt = (
                "Explain the business term the user is asking about in a concise way, "
                "then guide them back to the current intake question. "
                "Reply in the user's language: {language}."
            )
            redirect = state.next_question
            async for token in self._stream_with_prompt(
                prompt,
                history,
                f"{draft_response or ''} {redirect}".strip(),
                state,
                trace_tag="clarification",
            ):
                yield token
            return

        if reply_mode == ReplyMode.REDIRECT:
            prompt = (
                "Answer the user's off-topic question briefly in one sentence, "
                "then redirect them back to the active business energy intake task. "
                "Reply in the user's language: {language}."
            )
            redirect = f"After that, {state.next_question}"
            async for token in self._stream_with_prompt(
                prompt,
                history,
                redirect,
                state,
                trace_tag="redirect",
            ):
                yield token
            return

        async for token in self.stream_assistant_reply(
            latest_response=draft_response,
            state=state,
            history=history,
        ):
            yield token

    async def _stream_with_prompt(
        self,
        system_prompt: str,
        history: list[Message],
        fallback_text: str,
        state: ConversationState,
        trace_tag: str,
    ) -> AsyncIterator[str]:
        general_model = self._general_model

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder("history"),
                (
                    "system",
                    "Make sure the response accomplishes this goal: {goal}",
                ),
            ]
        )
        chain = prompt | general_model

        payload = {
            "language": self._language_instruction(state.detected_language),
            "history": to_langchain_messages(history[-16:]),
            "goal": fallback_text,
        }
        config = langsmith_config(
            "mode_response",
            tags=["response", trace_tag],
            metadata={"language": normalize_language_code(state.detected_language)},
        )
        async for chunk in self._astream_with_retry(chain, payload, config):
            text = chunk_to_text(chunk.content)
            if text:
                yield text

    async def _astream_with_retry(
        self,
        chain,
        payload: dict,
        config: dict,
    ) -> AsyncIterator:
        for attempt in range(3):
            yielded_any = False
            try:
                async for chunk in chain.astream(payload, config=config):
                    yielded_any = True
                    yield chunk
                return
            except Exception as exc:
                if yielded_any or not is_transient_llm_error(exc) or attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))

    def _language_instruction(self, language: str) -> str:
        return language_instruction(language)

    def _state_summary(self, state: ConversationState) -> str:
        profile = state.profile
        profile_parts = [
            f"business_segment={profile.business_segment.value if profile.business_segment else 'unknown'}",
            f"annual_usage_mwh={profile.annual_usage_mwh}",
            f"usage_estimated={profile.usage_estimated}",
            f"square_footage={profile.square_footage}",
            f"contract_status={profile.contract_status.value}",
            f"contract_expiry_months={profile.contract_expiry_months}",
            f"building_age_years={profile.building_age_years}",
        ]
        return (
            f"mode={state.mode.value}; "
            f"completed={state.completed}; "
            f"next_question={state.next_question}; "
            f"missing_fields={state.missing_fields}; "
            f"profile=({', '.join(profile_parts)})"
        )


llm_service = LLMService()
