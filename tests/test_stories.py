"""Community stories: writing, preview, review, reactions, replies, reports, deletion and photo privacy."""

import io
import re
from datetime import datetime

from PIL import Image

from app import db
from app import permissions as P
from app.models.audit import AuditEvent
from app.models.moderation import ModerationFlag
from app.models.story import Story, StoryImage, StoryReply
from app.services import stories as story_service
from tests.conftest import login, use_lang

BODY = "For months I told everyone I was fine. Writing it down was the first small step towards saying I was not."
STORY = {
    "title": "Everyone thought I was fine",
    "body": BODY,
    "topic": "wellbeing",
    "display_mode": "anonymous",
    "support_wanted": "listen",
    "reply_mode": "moderated",
    "content_warning": "none",
}


def submit(client, overrides=None, files=None):
    data = {**STORY, **(overrides or {}), "reviewed": "y"}
    if files:
        data["images"] = files
    return client.post("/voices/submit", data=data, content_type="multipart/form-data")


def received_codes(response) -> tuple[str, str]:
    page = response.get_data(as_text=True)
    reference = re.search(r"ST-[0-9A-Z]{4}-[0-9A-Z]{4}", page).group(0)
    code = re.findall(r'<dd class="reference-value">([0-9A-Z]{14})</dd>', page)[0]
    return reference, code


def publish(story: Story) -> None:
    moderator = login_as_moderator_user()
    story_service.review(story, moderator, "publish", None)


def login_as_moderator_user():
    from tests.conftest import user_by_role

    return user_by_role(P.ROLE_MODERATOR)


def jpeg_with_metadata() -> io.BytesIO:
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"  # camera make
    exif[0x0110] = "ModelX"  # camera model
    exif[0x8825] = {1: "N", 2: (23.0, 48.0, 0.0), 3: "E", 4: (90.0, 24.0, 0.0)}  # GPS: Dhaka
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 160, 130)).save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    return buf


# ---- Writing, previewing and sending ---------------------------------------------------------
def test_preview_shows_the_story_and_warns_about_identifiers(client):
    r = client.post("/voices/new", data={**STORY, "body": BODY + " Call me on 01712345678.", "action": "preview"})
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and "Everyone thought I was fine" in page
    assert 'name="body"' in page and r.headers["Cache-Control"] == "no-store"
    assert "redaction.kind_" not in page and Story.query.count() == 0
    assert "Phone number" in page and "Possible phone number" not in page
    assert story_service.identifier_warnings("01712345678 or +44 20 7946 0000") == ["phone"]


def test_sending_stores_a_pending_story_that_nobody_can_see(client):
    r = submit(client)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    reference, code = received_codes(r)
    story = Story.query.filter_by(reference=reference).one()
    assert story.status == "pending" and story.author_user_id is None and story.manage_hash != code
    assert client.get(f"/voices/{reference}").status_code == 404
    assert BODY not in client.get("/voices/").get_data(as_text=True)
    event = AuditEvent.query.filter_by(event_type="story.submitted").one()
    assert BODY not in (event.details or "") and event.ip_hash is None


def test_validation_explains_what_is_missing(client):
    r = client.post("/voices/new", data={**STORY, "body": "too short", "action": "preview"})
    assert "story.error_body_length" not in r.get_data(as_text=True) and r.status_code == 200
    r = client.post("/voices/new", data={**STORY, "display_mode": "chosen_name", "chosen_name": "", "action": "preview"})
    assert b"Enter your chosen name" in r.data
    r = client.post("/voices/new", data={**STORY, "display_mode": "account_name", "action": "preview"})
    assert b"Sign in to use your account name" in r.data
    r = client.post("/voices/submit", data=STORY)
    assert r.status_code == 422 and b"Tick this box before sending" in r.data
    r = submit(client, {"website": "http://spam.example"})
    assert r.status_code == 422 and Story.query.count() == 0


def test_account_name_links_the_story_only_when_chosen(client):
    user = login(client, P.ROLE_REPORTER)
    reference, _ = received_codes(submit(client, {"display_mode": "account_name"}))
    assert Story.query.filter_by(reference=reference).one().author_user_id == user.id
    reference, _ = received_codes(submit(client))
    assert Story.query.filter_by(reference=reference).one().author_user_id is None


# ---- Review and publishing -------------------------------------------------------------------
def test_moderator_publishes_and_the_story_appears_with_its_content_note(client):
    reference, _ = received_codes(submit(client, {"content_warning": "grief"}))
    story = Story.query.filter_by(reference=reference).one()
    login(client, P.ROLE_MODERATOR)
    assert client.get("/workspace/stories").status_code == 200
    r = client.post(f"/workspace/stories/{story.id}", data={"decision": "publish", "reason": ""})
    assert r.status_code == 302 and Story.query.get(story.id).status == "published"
    page = client.get(f"/voices/{reference}").get_data(as_text=True)
    assert '<details class="cw">' in page and "Grief or loss" in page and BODY in page
    assert reference in client.get("/voices/?topic=wellbeing").get_data(as_text=True)
    assert AuditEvent.query.filter_by(event_type="story.published", target_id=story.id).count() == 1


def test_turning_down_or_taking_down_needs_a_reason(client):
    reference, _ = received_codes(submit(client))
    story = Story.query.filter_by(reference=reference).one()
    login(client, P.ROLE_SUPERVISOR)
    client.post(f"/workspace/stories/{story.id}", data={"decision": "reject", "reason": ""})
    assert Story.query.get(story.id).status == "pending"
    client.post(f"/workspace/stories/{story.id}", data={"decision": "publish"})
    client.post(f"/workspace/stories/{story.id}", data={"decision": "take_down", "reason": "Names a private person"})
    taken = Story.query.get(story.id)
    assert taken.status == "rejected" and taken.review_reason == "Names a private person"
    assert client.get(f"/voices/{reference}").status_code == 404


def test_only_moderators_and_supervisors_review_stories(client):
    for role in (P.ROLE_ADMIN, P.ROLE_SUPPORT, P.ROLE_EDITORIAL):
        login(client, role)
        assert client.get("/workspace/stories").status_code == 403, role
        client.post("/auth/logout")
    assert P.STORY_MODERATE in P.ROLE_PERMISSIONS[P.ROLE_MODERATOR] and P.STORY_MODERATE in P.ROLE_PERMISSIONS[P.ROLE_SUPERVISOR]


# ---- Reactions, replies and reports ----------------------------------------------------------
def test_reactions_count_once_per_visitor(client):
    reference, _ = received_codes(submit(client))
    story = Story.query.filter_by(reference=reference).one()
    assert client.post(f"/voices/{reference}/react", data={"kind": "hear_you"}).status_code == 404
    publish(story)
    for _ in range(3):
        client.post(f"/voices/{reference}/react", data={"kind": "hear_you"})
    client.post(f"/voices/{reference}/react", data={"kind": "made_up"})
    db.session.refresh(story)
    assert story.hear_you == 1 and story.not_alone == 0


def test_replies_wait_for_a_moderator(client):
    reference, _ = received_codes(submit(client))
    story = Story.query.filter_by(reference=reference).one()
    publish(story)
    client.post(f"/voices/{reference}/reply", data={"body": "I hear you. It took me years too.", "display_name": ""})
    reply = StoryReply.query.one()
    assert reply.status == "pending" and "It took me years too" not in client.get(f"/voices/{reference}").get_data(as_text=True)
    login(client, P.ROLE_MODERATOR)
    client.post(f"/workspace/stories/replies/{reply.id}", data={"decision": "publish", "reason": ""})
    client.post("/auth/logout")
    assert "It took me years too" in client.get(f"/voices/{reference}").get_data(as_text=True)


def test_replies_can_be_turned_off(client):
    reference, _ = received_codes(submit(client, {"reply_mode": "off"}))
    publish(Story.query.filter_by(reference=reference).one())
    client.post(f"/voices/{reference}/reply", data={"body": "Hello there"})
    assert StoryReply.query.count() == 0
    assert b"turned replies off" in client.get(f"/voices/{reference}").data


def test_visitors_can_report_a_story_to_the_moderation_queue(client):
    reference, _ = received_codes(submit(client))
    story = Story.query.filter_by(reference=reference).one()
    publish(story)
    r = client.post("/voices/report", data={"target": "story", "target_id": story.id, "reason": "doxxing", "notes": ""})
    assert r.status_code == 302
    flag = ModerationFlag.query.one()
    assert flag.target_type == "story" and flag.target_id == story.id and flag.raised_by_id is None
    login(client, P.ROLE_MODERATOR)
    assert f"/workspace/stories/{story.id}".encode() in client.get("/workspace/moderation").data


def test_pending_stories_cannot_be_reported_or_replied_to(client):
    reference, _ = received_codes(submit(client))
    story = Story.query.filter_by(reference=reference).one()
    assert client.post("/voices/report", data={"target": "story", "target_id": story.id, "reason": "spam"}).status_code == 404
    assert client.post(f"/voices/{reference}/reply", data={"body": "Hello"}).status_code == 404


# ---- The writer deletes their own story -----------------------------------------------------
def test_writer_can_check_and_delete_with_the_code(client):
    reference, code = received_codes(submit(client, files=[(jpeg_with_metadata(), "photo.jpg")]))
    story = Story.query.filter_by(reference=reference).one()
    publish(story)
    client.post(f"/voices/{reference}/reply", data={"body": "Sending care."})
    assert (
        b"No story matches" in client.post("/voices/manage", data={"reference": reference, "code": "WRONGCODE12345", "action": "open"}).data
    )
    r = client.post("/voices/manage", data={"reference": reference.lower(), "code": code.lower(), "action": "open"})
    assert b"Published" in r.data and r.headers["Cache-Control"] == "no-store"
    client.post("/voices/manage", data={"reference": reference, "code": code, "action": "delete"})
    assert Story.query.count() == 1
    r = client.post("/voices/manage", data={"reference": reference, "code": code, "action": "delete", "confirm": "y"})
    assert b"have been deleted" in r.data
    assert Story.query.count() == 0 and StoryImage.query.count() == 0 and StoryReply.query.count() == 0
    assert AuditEvent.query.filter_by(event_type="story.deleted_by_writer").count() == 1


# ---- Photos ----------------------------------------------------------------------------------
def test_photos_lose_their_metadata_and_stay_private_until_published(client):
    reference, _ = received_codes(submit(client, files=[(jpeg_with_metadata(), "photo.jpg")]))
    image = StoryImage.query.one()
    stored = story_service.image_bytes(image)
    assert b"SecretPhoneMaker" not in stored and b"ModelX" not in stored
    with Image.open(io.BytesIO(stored)) as img:
        assert not img.getexif() and img.format == "JPEG"
    assert image.data_enc != stored
    assert client.get(f"/voices/image/{image.id}").status_code == 404
    login(client, P.ROLE_MODERATOR)
    r = client.get(f"/voices/image/{image.id}")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store" and r.mimetype == "image/jpeg"
    client.post("/auth/logout")
    publish(image.story)
    r = client.get(f"/voices/image/{image.id}")
    assert r.status_code == 200 and "public" in r.headers["Cache-Control"]


def test_non_images_and_too_many_photos_are_refused(client):
    r = submit(client, files=[(io.BytesIO(b"%PDF-1.4 not a photo"), "photo.jpg")])
    assert r.status_code == 422 and b"be opened as a photo" in r.data
    r = submit(client, files=[(jpeg_with_metadata(), f"p{i}.jpg") for i in range(4)])
    assert r.status_code == 422 and b"up to three photos" in r.data
    assert Story.query.count() == 0


# ---- Pages, language and accountability ------------------------------------------------------
def test_home_stories_and_accountability_pages_render_in_both_languages(client):
    for lang, needle in (("en", "Share your story"), ("bn", "আপনার গল্প লিখুন")):
        use_lang(client, lang)
        for path in ("/", "/voices/", "/voices/new", "/voices/manage", "/accountability"):
            r = client.get(path)
            assert r.status_code == 200, (lang, path)
        assert needle in client.get("/").get_data(as_text=True)
    page = client.get("/accountability").get_data(as_text=True)
    assert "যাচাই হয়নি এমন অভিযোগ" in page and "নিশ্চিত আইনি ফলাফল" in page


def test_the_offline_cache_never_keeps_writer_pages(client):
    sw = client.get("/sw.js").get_data(as_text=True)
    for path in ("/voices/new", "/voices/submit", "/voices/manage"):
        assert f'"{path}"' in sw
    for path in ("/voices/new", "/voices/manage"):
        assert client.get(path).headers["Cache-Control"] == "no-store"


def test_dates_follow_the_page_language(client):
    reference, _ = received_codes(submit(client))
    story = Story.query.filter_by(reference=reference).one()
    publish(story)
    story.published_at = datetime(2026, 10, 3, 14, 5)
    db.session.commit()
    use_lang(client, "en")
    assert "03 Oct 2026" in client.get(f"/voices/{reference}").get_data(as_text=True)
    use_lang(client, "bn")
    page = client.get(f"/voices/{reference}").get_data(as_text=True)
    assert "৩ অক্টোবর ২০২৬" in page and "Oct" not in page


def test_new_report_categories_are_offered_and_routed(client):
    page = client.get("/report/1").get_data(as_text=True)
    assert 'value="stalking"' in page and 'value="hate_incident"' in page
    assert P.default_department_for_category("hate_incident") == P.DEPT_SUPPORT and "stalking" in P.CATEGORIES
