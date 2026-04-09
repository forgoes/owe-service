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
                    "You are an energy sales qualification assistant. "
                    "Keep responses concise, professional, and action-oriented. "
                    "Use the provided lead state and next question. "
                    "Do not invent profile fields that are still missing. "
                    "Reply in the user's language: {language}.",
                ),
                MessagesPlaceholder("history"),
                (
                    "system",
                    "Current state: {state_json}\nDraft response to refine: {draft_response}",
                ),
            ]
        )

        chain = prompt | qualification_model
        payload = {
            "language": self._language_instruction(state.detected_language),
            "history": to_langchain_messages(history[-8:]),
            "state_json": state.model_dump_json(),
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
                "Reply like a helpful general assistant for a product that specializes in energy lead qualification. "
                "Answer the user's actual question first. "
                "Stay grounded in this product's scope and avoid generic 'ask me anything' guidance unless the user truly asks for broad assistant capabilities. "
                "If the question needs real-time information you do not have, say so plainly and helpfully. "
                "Do not force the conversation into the energy qualification workflow unless the user asks about it. "
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
                "Reply like a concise product specialist for an energy lead qualification assistant. "
                "Explain clearly what the product does, who it is for, and what kinds of information it can evaluate. "
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
                "then guide them back to the current qualification question. "
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
                "then redirect them back to the active energy lead qualification task. "
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
            "history": to_langchain_messages(history[-8:]),
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


llm_service = LLMService()
