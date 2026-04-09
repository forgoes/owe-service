from __future__ import annotations

from collections.abc import Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.runtime.openai import chat_model_registry
from app.runtime.config import settings
from app.schemas.chat import Message


def get_chat_model(*, temperature: float | None = None) -> ChatOpenAI:
    model = chat_model_registry.get()
    if temperature is None:
        return model
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=temperature,
    )


def to_langchain_messages(history: Iterable[Message]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        elif item.role == "assistant":
            messages.append(AIMessage(content=item.content))
        else:
            messages.append(SystemMessage(content=item.content))
    return messages


def chunk_to_text(content: object) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return ""
