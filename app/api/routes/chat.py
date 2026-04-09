from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.repositories.conversation_repository import conversation_repository
from app.schemas.chat import ChatRequest, ConversationSession, LeadProfile, Message, ReplyMode
from app.services.graph import run_lead_agent
from app.services.llm import llm_service

router = APIRouter(tags=["chat"])
LLM_FAILURE_MESSAGE = "I couldn't process your last message reliably just now. Please try again in a moment."


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    existing_record = await conversation_repository.load(request.session_id)
    server_history = existing_record.messages if existing_record else (request.history or [])
    server_profile = existing_record.state.profile if existing_record else (request.profile or LeadProfile())
    previous_state = existing_record.state if existing_record else None

    normalized_request = request.model_copy(
        update={
            "history": server_history,
            "profile": server_profile,
        }
    )
    outcome = run_lead_agent(normalized_request, previous_state=previous_state)
    combined_history = [*server_history, Message(role="user", content=request.message)]

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("state", outcome.state.model_dump(mode="json"))
        if outcome.reply_mode == ReplyMode.ERROR:
            yield _sse("done", {"message": outcome.assistant_message})
            return
        accumulated = ""
        try:
            async for token in llm_service.stream_mode_reply(
                reply_mode=outcome.reply_mode,
                draft_response=outcome.assistant_message,
                state=outcome.state,
                history=combined_history,
            ):
                accumulated += token
                yield _sse("token", {"delta": token})
        except Exception as exc:
            final_messages = [
                *combined_history,
            ]
            await conversation_repository.save(
                session_id=request.session_id,
                state=outcome.state,
                messages=final_messages,
            )
            yield _sse("error", {"message": str(exc)})
            yield _sse("done", {"message": LLM_FAILURE_MESSAGE})
            return

        final_messages = [
            *combined_history,
            Message(
                role="assistant",
                content=accumulated or outcome.assistant_message or outcome.state.next_question,
            ),
        ]
        await conversation_repository.save(
            session_id=request.session_id,
            state=outcome.state,
            messages=final_messages,
        )
        yield _sse(
            "done",
            {
                "message": accumulated or outcome.assistant_message or outcome.state.next_question,
            },
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/chat/{session_id}")
async def get_chat_session(session_id: str) -> ConversationSession | dict[str, str]:
    record = await conversation_repository.load(session_id)
    if record is None:
        return {"status": "not_found"}

    return ConversationSession(state=record.state, messages=record.messages)
