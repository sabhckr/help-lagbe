"""Community stories: creation, photo cleaning, review, reactions, replies, reports and deletion.

Nothing a visitor writes is public until a moderator approves it. Every staff decision is audited.
Audit entries never contain story text.
"""

from __future__ import annotations

import hashlib
import hmac
import io
from datetime import timedelta

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from app.crypto import decrypt_bytes, encrypt_bytes, hash_secret
from app.extensions import db
from app.models.base import random_reference, random_secret, utcnow
from app.models.moderation import ModerationFlag
from app.models.story import PENDING, PUBLISHED, REACTIONS, REJECTED, Story, StoryImage, StoryReply
from app.services import audit
from app.services.redaction import scan_for_identifiers

MAX_SIDE = 1600
MAX_PIXELS = 40_000_000
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
SESSION_REACTIONS = "story_reactions"


class StoryImageError(Exception):
    """Raised with a translation key when a photo cannot be accepted."""


def identifier_warnings(*texts: str | None) -> list[str]:
    """Kinds of identifying detail found in the text (phone numbers, emails, ID numbers, links...)."""
    kinds: list[str] = []
    for text in texts:
        for finding in scan_for_identifiers(text or ""):
            if finding.kind not in kinds:
                kinds.append(finding.kind)
    # A Bangladeshi mobile number also matches the generic pattern; one line about it is enough.
    if "phone_generic" in kinds and ("phone" in kinds or "bn_phone" in kinds):
        kinds.remove("phone_generic")
    return kinds


def clean_image(file: FileStorage) -> tuple[bytes, str, int, int]:
    """Decode a photo and re-encode only its pixels, so EXIF, GPS and other metadata are dropped."""
    limit = current_app.config["STORY_IMAGE_MAX_BYTES"]
    raw = file.stream.read(limit + 1)
    if not raw:
        raise StoryImageError("upload.error_empty")
    if len(raw) > limit:
        raise StoryImageError("story.image_error_size")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ACCEPTED_FORMATS:
            raise StoryImageError("story.image_error_type")
        with Image.open(io.BytesIO(raw)) as img:
            if img.width * img.height > MAX_PIXELS:
                raise StoryImageError("story.image_error_type")
            upright = ImageOps.exif_transpose(img)
            upright.thumbnail((MAX_SIDE, MAX_SIDE))
            has_alpha = upright.mode in ("RGBA", "LA") or (upright.mode == "P" and "transparency" in upright.info)
            clean = upright.convert("RGBA" if has_alpha else "RGB")
            clean.info = {}
            out = io.BytesIO()
            if has_alpha:
                clean.save(out, format="PNG", optimize=True)
                mime = "image/png"
            else:
                clean.save(out, format="JPEG", quality=85, optimize=True)
                mime = "image/jpeg"
            width, height = clean.size
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise StoryImageError("story.image_error_type") from exc
    return out.getvalue(), mime, width, height


def _unique_reference() -> str:
    while True:
        ref = random_reference("ST")
        if not Story.query.filter_by(reference=ref).first():
            return ref


def create(data: dict, images: list[FileStorage], *, author=None, language: str = "bn") -> tuple[Story, str]:
    """Store a story for review. Returns (story, management code); the code is shown once, kept only as a hash."""
    cleaned = [clean_image(f) for f in images if f and f.filename][: current_app.config["STORY_MAX_IMAGES"]]
    code = random_secret()
    display_mode = data["display_mode"]
    story = Story(
        reference=_unique_reference(),
        manage_hash=hash_secret(code),
        title=(data.get("title") or "").strip() or None,
        body=data["body"].strip(),
        topic=data["topic"],
        display_mode=display_mode,
        chosen_name=(data.get("chosen_name") or "").strip() or None if display_mode == "chosen_name" else None,
        author_user_id=author.id if display_mode == "account_name" and author is not None else None,
        support_wanted=data["support_wanted"],
        reply_mode=data["reply_mode"],
        content_warning=data["content_warning"],
        image_description=(data.get("image_description") or "").strip() or None,
        language=language,
    )
    for blob, mime, width, height in cleaned:
        story.images.append(
            StoryImage(
                mime_type=mime,
                width=width,
                height=height,
                size_bytes=len(blob),
                sha256=hashlib.sha256(blob).hexdigest(),
                data_enc=encrypt_bytes(blob),
            )
        )
    db.session.add(story)
    db.session.flush()
    audit.record("story.submitted", target_type="story", target_id=story.id, details={"topic": story.topic, "images": len(cleaned)})
    db.session.commit()
    return story, code


def find_for_writer(reference: str, code: str) -> Story | None:
    story = Story.query.filter_by(reference=(reference or "").strip().upper()).first()
    if story is None or not hmac.compare_digest(story.manage_hash, hash_secret((code or "").strip().upper())):
        return None
    return story


def delete_by_writer(story: Story) -> None:
    """The writer's own deletion: the story, its photos and replies are removed for good."""
    audit.record("story.deleted_by_writer", target_type="story", target_id=story.id, details={"was": story.status})
    db.session.delete(story)
    db.session.commit()


def review(story: Story, user, decision: str, reason: str | None) -> None:
    """decision: publish, reject, or take_down (for a story that is already public)."""
    story.status = PUBLISHED if decision == "publish" else REJECTED
    story.review_reason = (reason or "").strip() or None
    story.reviewed_by_id = user.id
    story.reviewed_at = utcnow()
    if decision == "publish":
        story.published_at = story.published_at or utcnow()
    event = {"publish": "story.published", "reject": "story.rejected", "take_down": "story.taken_down"}[decision]
    audit.record(event, actor=user, target_type="story", target_id=story.id, reason=story.review_reason)
    db.session.commit()


def review_reply(reply: StoryReply, user, decision: str, reason: str | None) -> None:
    reply.status = PUBLISHED if decision == "publish" else REJECTED
    reply.review_reason = (reason or "").strip() or None
    reply.reviewed_by_id = user.id
    reply.reviewed_at = utcnow()
    event = "story_reply.published" if decision == "publish" else "story_reply.rejected"
    audit.record(event, actor=user, target_type="story_reply", target_id=reply.id, reason=reply.review_reason)
    db.session.commit()


def react(story: Story, kind: str, session) -> bool:
    """Count one supportive reaction per kind, per story, per browser session."""
    if kind not in REACTIONS or story.status != PUBLISHED:
        return False
    key = f"{story.id}:{kind}"
    seen = list(session.get(SESSION_REACTIONS, []))
    if key in seen:
        return False
    column = getattr(Story, kind)
    Story.query.filter_by(id=story.id).update({column: column + 1}, synchronize_session=False)
    db.session.commit()
    session[SESSION_REACTIONS] = (seen + [key])[-200:]
    return True


def reacted(story: Story, session) -> set[str]:
    prefix = f"{story.id}:"
    return {k[len(prefix) :] for k in session.get(SESSION_REACTIONS, []) if k.startswith(prefix)}


def add_reply(story: Story, body: str, display_name: str | None) -> StoryReply:
    reply = StoryReply(story_id=story.id, body=body.strip(), display_name=(display_name or "").strip() or None)
    db.session.add(reply)
    db.session.flush()
    audit.record("story_reply.submitted", target_type="story_reply", target_id=reply.id, details={"story": story.id})
    db.session.commit()
    return reply


def report(target_type: str, target_id: int, reason: str, notes: str | None) -> ModerationFlag:
    """A visitor reports a story or reply; it lands in the moderation queue."""
    flag = ModerationFlag(
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        notes=(notes or "").strip() or "Reported by a visitor",
    )
    db.session.add(flag)
    db.session.flush()
    audit.record("moderation.flagged", target_type=target_type, target_id=target_id, details={"reason": reason, "by": "visitor"})
    db.session.commit()
    return flag


def image_bytes(image: StoryImage) -> bytes:
    return decrypt_bytes(image.data_enc)


def purge_rejected(days: int = 30) -> int:
    """Delete stories and replies that were turned down more than `days` ago."""
    cutoff = utcnow() - timedelta(days=days)
    stories = Story.query.filter(Story.status == REJECTED, Story.reviewed_at < cutoff).all()
    replies = StoryReply.query.filter(StoryReply.status == REJECTED, StoryReply.reviewed_at < cutoff).all()
    for item in [*stories, *replies]:
        db.session.delete(item)
    db.session.commit()
    return len(stories) + len(replies)


def pending_counts() -> dict[str, int]:
    return {
        "stories": Story.query.filter_by(status=PENDING).count(),
        "replies": StoryReply.query.filter_by(status=PENDING).count(),
    }
