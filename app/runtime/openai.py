from __future__ import annotations

from app.runtime.config import settings
from langchain_openai import ChatOpenAI


class ChatModelRegistry:
    def __init__(self) -> None:
        self._model: ChatOpenAI | None = None
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required to initialize chat models.")

        if not settings.openai_model:
            raise RuntimeError("OPENAI_MODEL must be configured before startup.")

        try:
            model = ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                temperature=0.0,
            )
            if settings.model_startup_probe:
                model.invoke("Reply with OK.")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize configured model '{settings.openai_model}'."
            ) from exc

        self._model = model
        self._initialized = True

    def get(self) -> ChatOpenAI:
        return self._model

    def is_initialized(self) -> bool:
        return self._initialized


chat_model_registry = ChatModelRegistry()
