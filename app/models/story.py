"""Community life stories. Written by anyone, shown publicly only after a moderator approves them.

An anonymous story is never linked to an account. The writer gets a reference and a one-time code,
stored only as a hash, which lets them delete the story later. Photos are re-encoded without
metadata and stored encrypted, like evidence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Model
from app.models.base import utcnow

STORY_TOPICS = (
    "family_relationships",
    "wellbeing",
    "identity_belonging",
    "harassment_recovery",
    "support_connection",
    "hope_healing",
)
STORY_DISPLAY_MODES = ("anonymous", "chosen_name", "account_name")
STORY_SUPPORT = ("listen", "advice", "similar", "resources")
STORY_REPLY_MODES = ("moderated", "off")
STORY_WARNINGS = ("none", "mental_health", "harassment_abuse", "violence", "grief", "other")
REACTIONS = ("hear_you", "not_alone", "thank_you")

PENDING, PUBLISHED, REJECTED = "pending", "published", "rejected"


class Story(Model):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    manage_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="anonymous")
    chosen_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Set only when the writer chose to appear under their account name.
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    support_wanted: Mapped[str] = mapped_column(String(16), nullable=False)
    reply_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="moderated")
    content_warning: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    image_description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="bn")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING, index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    hear_you: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_alone: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    thank_you: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    author = relationship("User", foreign_keys=[author_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    images: Mapped[list[StoryImage]] = relationship(back_populates="story", cascade="all, delete-orphan", order_by="StoryImage.id")
    replies: Mapped[list[StoryReply]] = relationship(back_populates="story", cascade="all, delete-orphan", order_by="StoryReply.id")

    @property
    def display_name(self) -> str | None:
        """The name shown publicly, or None for an anonymous story."""
        if self.display_mode == "chosen_name" and self.chosen_name:
            return self.chosen_name
        if self.display_mode == "account_name" and self.author is not None:
            return self.author.name
        return None

    @property
    def published_replies(self) -> list[StoryReply]:
        return [r for r in self.replies if r.status == PUBLISHED]

    def reading_minutes(self) -> int:
        return max(1, round(len(self.body.split()) / 180))


class StoryReply(Model):
    __tablename__ = "story_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING, index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    story: Mapped[Story] = relationship(back_populates="replies")
    reviewed_by = relationship("User")


class StoryImage(Model):
    __tablename__ = "story_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    data_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    story: Mapped[Story] = relationship(back_populates="images")
