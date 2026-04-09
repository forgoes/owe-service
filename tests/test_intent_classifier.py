from app.services.intent_classifier import IntentClassification


def test_language_codes_are_normalized() -> None:
    result = IntentClassification.model_validate(
        {"intent": "general_chat", "language": "es-ES"}
    )

    assert result.language == "es"
