from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import delete

from app.db.models import Conversation, ConversationMessage, LeadProfileRecord, QualificationDecision
from app.runtime.session import SessionLocal
from app.schemas.chat import ConversationState, Message
from app.schemas.chat import (
    ContractStatus,
    ConversationMode,
    IntentType,
    LeadBucket,
    LeadProfile,
    QualificationResult,
    QualificationTier,
)
from app.services.language import normalize_language_code


@dataclass
class ConversationRecord:
    state: ConversationState
    messages: list[Message] = field(default_factory=list)


def _serialize_profile(profile: LeadProfile) -> dict[str, object]:
    return {
        "business_segment": profile.business_segment.value if profile.business_segment else None,
        "annual_usage_mwh": profile.annual_usage_mwh,
        "usage_estimated": profile.usage_estimated,
        "square_footage": profile.square_footage,
        "contract_status": profile.contract_status.value,
        "contract_expiry_months": profile.contract_expiry_months,
        "building_age_years": profile.building_age_years,
        "has_current_provider": profile.has_current_provider,
        "notes_json": json.dumps(profile.notes),
    }


def _deserialize_profile(record: LeadProfileRecord | None) -> LeadProfile:
    if record is None:
        return LeadProfile()
    return LeadProfile(
        business_segment=record.business_segment,
        annual_usage_mwh=record.annual_usage_mwh,
        usage_estimated=record.usage_estimated,
        square_footage=record.square_footage,
        contract_status=ContractStatus(record.contract_status),
        contract_expiry_months=record.contract_expiry_months,
        building_age_years=record.building_age_years,
        has_current_provider=record.has_current_provider,
        notes=json.loads(record.notes_json) if record.notes_json else [],
    )


def _deserialize_qualification(record: QualificationDecision | None) -> QualificationResult:
    if record is None:
        return QualificationResult(reasoning="Lead is not qualified yet because discovery is incomplete.")
    return QualificationResult(
        tier=QualificationTier(record.tier),
        bucket=LeadBucket(record.bucket),
        reasoning=record.reasoning,
    )


class ConversationRepository:
    @staticmethod
    async def load(session_id: str) -> ConversationRecord | None:
        with SessionLocal() as session:
            conversation = session.get(Conversation, session_id)
            if conversation is None:
                return None

            messages = [
                Message(role=item.role, content=item.content)
                for item in sorted(conversation.messages, key=lambda message: message.sequence)
            ]
            state = ConversationState(
                session_id=conversation.session_id,
                mode=ConversationMode(conversation.mode),
                detected_language=normalize_language_code(conversation.detected_language),
                profile=_deserialize_profile(conversation.lead_profile),
                qualification=_deserialize_qualification(conversation.qualification_decision),
                missing_fields=json.loads(conversation.missing_fields_json),
                next_question=conversation.next_question,
                completed=conversation.qualification_decision.completed
                if conversation.qualification_decision
                else False,
                last_intent=IntentType(conversation.last_intent) if conversation.last_intent else None,
            )
            return ConversationRecord(state=state, messages=messages)

    @staticmethod
    async def save(
        session_id: str, state: ConversationState, messages: list[Message]
    ) -> None:
        with SessionLocal() as session:
            conversation = session.get(Conversation, session_id)
            if conversation is None:
                conversation = Conversation(session_id=session_id)
                session.add(conversation)
                session.flush()

            conversation.mode = state.mode.value
            conversation.detected_language = normalize_language_code(state.detected_language)
            conversation.missing_fields_json = json.dumps(state.missing_fields)
            conversation.next_question = state.next_question
            conversation.last_intent = state.last_intent.value if state.last_intent else None

            if conversation.lead_profile is None:
                conversation.lead_profile = LeadProfileRecord(conversation_id=session_id)

            for key, value in _serialize_profile(state.profile).items():
                setattr(conversation.lead_profile, key, value)

            if conversation.qualification_decision is None:
                conversation.qualification_decision = QualificationDecision(conversation_id=session_id)

            conversation.qualification_decision.tier = state.qualification.tier.value
            conversation.qualification_decision.bucket = state.qualification.bucket.value
            conversation.qualification_decision.reasoning = state.qualification.reasoning
            conversation.qualification_decision.completed = state.completed

            session.execute(
                delete(ConversationMessage).where(ConversationMessage.conversation_id == session_id)
            )
            session.flush()
            for sequence, message in enumerate(messages, start=1):
                session.add(
                    ConversationMessage(
                        conversation_id=session_id,
                        sequence=sequence,
                        role=message.role,
                        content=message.content,
                    )
                )

            session.commit()

    @staticmethod
    async def clear(session_id: str) -> None:
        with SessionLocal() as session:
            conversation = session.get(Conversation, session_id)
            if conversation is not None:
                session.delete(conversation)
                session.commit()


conversation_repository = ConversationRepository()
