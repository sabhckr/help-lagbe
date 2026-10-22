from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

PRESENCE_AVAILABLE = "available"
PRESENCE_BUSY = "busy"
PRESENCE_OFFLINE = "offline"

CONV_WAITING = "waiting"
CONV_ACTIVE = "active"
CONV_CLOSED = "closed"


class AgentPresence(Model):
    """Real presence: an agent is only "available" while they have said so AND have been
    seen within SUPPORT_PRESENCE_TIMEOUT_SECONDS. Nothing here is simulated."""

    __tablename__ = "agent_presence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PRESENCE_OFFLINE)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = relationship("User")


class SupportConversation(Model):
    __tablename__ = "support_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CONV_WAITING, index=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    topic: Mapped[str | None] = mapped_column(String(40), nullable=True)
    visitor_label: Mapped[str] = mapped_column(String(40), nullable=False, default="Visitor")
    safety_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    escalated_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    consent_follow_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    follow_up_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_visitor_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(16), nullable=True)  # visitor | agent | system
    close_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    agent = relationship("User", foreign_keys=[agent_id])
    escalated_to = relationship("User", foreign_keys=[escalated_to_id])
    linked_case = relationship("Case")
    messages: Mapped[list[SupportMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="SupportMessage.created_at"
    )

    @property
    def is_open(self) -> bool:
        return self.status != CONV_CLOSED


class SupportMessage(Model):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("support_conversations.id"), nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)  # visitor | agent | system
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)

    conversation: Mapped[SupportConversation] = relationship(back_populates="messages")
    sender = relationship("User")
