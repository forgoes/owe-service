from app.runtime.openai import ChatModelRegistry, chat_model_registry

model_registry = chat_model_registry

__all__ = ["ChatModelRegistry", "model_registry", "chat_model_registry"]
