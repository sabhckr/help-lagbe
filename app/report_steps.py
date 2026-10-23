"""The six reporting steps: which fields each step saves, and how each value is checked.

Pure functions only. Nothing here touches the database, so each rule can be tested directly.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app import permissions as P
from app.models.case import (
    CONTACT_EMAIL,
    CONTACT_PHONE,
    CONTACT_TRACKING,
    DANGER_NO,
    DANGER_UNSURE,
    DANGER_YES,
    SUBMISSION_ANONYMOUS,
    SUBMISSION_CONFIDENTIAL,
)

STEP_COUNT = 6
STEP_TITLES = {
    1: "step.1.title",
    2: "step.2.title",
    3: "step.3.title",
    4: "step.4.title",
    5: "step.5.title",
    6: "step.6.title",
}
MAX_NARRATIVE = 20000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{6,20}$")
BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Short English titles stored on the case. Staff see these; reporters never see the internal key.
CATEGORY_TITLES = {
    "harassment": "Harassment or bullying",
    "threats_blackmail": "Threats or blackmail",
    "abuse_violence": "Abuse or violence",
    "corruption_exploitation": "Corruption or exploitation",
    "online_harm": "Online harm",
    "child_safety": "Child safety concern",
    "other": "Something else",
    "not_sure": "Not sure yet",
}

FIELDS_BY_STEP = {
    1: ("category",),
    2: ("immediate_danger", "child_involved"),
    3: ("narrative", "approximate_time", "location_text"),
    4: (
        "submission_type",
        "identity_name",
        "identity_phone",
        "identity_email",
        "contact_preference",
        "safe_hours",
        "do_not_contact",
        "safe_contact_notes",
        "consent_contact",
    ),
    5: (),
    6: ("consent_process", "consent_publication"),
}


class StepError(ValueError):
    """Raised by callers that need a single message key; validation itself returns a dict."""


def _text(form: Mapping[str, Any], key: str) -> str:
    return (form.get(key) or "").strip()


def validate(step: int, form: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (values to save, errors). Errors map a field name to a translation key."""
    if step == 1:
        category = _text(form, "category")
        if category not in P.CATEGORIES:
            return {}, {"category": "report.error_category"}
        return {"category": category}, {}

    if step == 2:
        danger = _text(form, "immediate_danger")
        if danger not in (DANGER_YES, DANGER_NO, DANGER_UNSURE):
            return {}, {"immediate_danger": "report.error_danger"}
        child = "y" if form.get("child_involved") == "y" else ""
        return {"immediate_danger": danger, "child_involved": child}, {}

    if step == 3:
        narrative = _text(form, "narrative")
        errors: dict[str, str] = {}
        if len(narrative) < 10:
            errors["narrative"] = "report.error_narrative_short"
        elif len(narrative) > MAX_NARRATIVE:
            errors["narrative"] = "report.error_narrative_long"
        approximate_time = _text(form, "approximate_time")
        location_text = _text(form, "location_text")
        if len(approximate_time) > 120:
            errors["approximate_time"] = "validation.too_long"
        if len(location_text) > 200:
            errors["location_text"] = "validation.too_long"
        return {"narrative": narrative, "approximate_time": approximate_time, "location_text": location_text}, errors

    if step == 4:
        return _validate_contact(form)

    if step == 5:
        return {}, {}

    if step == 6:
        if _text(form, "consent_process") != "y":
            return {}, {"consent_process": "report.error_consent"}
        values = {"consent_process": "y", "consent_publication": "y" if form.get("consent_publication") == "y" else ""}
        return values, {}

    raise StepError(f"unknown step {step}")


def _validate_contact(form: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    submission_type = _text(form, "submission_type")
    if submission_type not in (SUBMISSION_ANONYMOUS, SUBMISSION_CONFIDENTIAL):
        return {}, {"submission_type": "report.error_submission_type"}

    if submission_type == SUBMISSION_ANONYMOUS:
        # Anonymous means no identity and no contact details are held at all.
        values = {
            "submission_type": SUBMISSION_ANONYMOUS,
            "identity_name": "",
            "identity_phone": "",
            "identity_email": "",
            "contact_preference": CONTACT_TRACKING,
            "safe_hours": "",
            "do_not_contact": "",
            "safe_contact_notes": "",
            "consent_contact": "",
        }
        return values, {}

    errors: dict[str, str] = {}
    details: dict[str, Any] = {
        "submission_type": SUBMISSION_CONFIDENTIAL,
        "identity_name": _text(form, "identity_name"),
        "identity_phone": _text(form, "identity_phone").translate(BENGALI_DIGITS),
        "identity_email": _text(form, "identity_email"),
        "contact_preference": _text(form, "contact_preference") or CONTACT_TRACKING,
        "safe_hours": _text(form, "safe_hours"),
        "do_not_contact": _text(form, "do_not_contact"),
        "safe_contact_notes": _text(form, "safe_contact_notes"),
        "consent_contact": "y" if form.get("consent_contact") == "y" else "",
    }
    if len(details["identity_name"]) > 120:
        errors["identity_name"] = "validation.too_long"
    if details["identity_phone"] and not PHONE_RE.match(details["identity_phone"]):
        errors["identity_phone"] = "validation.phone"
    if details["identity_email"] and not EMAIL_RE.match(details["identity_email"]):
        errors["identity_email"] = "validation.email"
    if len(details["safe_hours"]) > 120 or len(details["do_not_contact"]) > 300 or len(details["safe_contact_notes"]) > 1000:
        errors["safe_contact_notes"] = "validation.too_long"
    preference = details["contact_preference"]
    if preference not in (CONTACT_TRACKING, CONTACT_PHONE, CONTACT_EMAIL, "none"):
        errors["contact_preference"] = "validation.required"
    if preference == CONTACT_PHONE and not details["identity_phone"] and "identity_phone" not in errors:
        errors["identity_phone"] = "report.error_need_phone"
    if preference == CONTACT_EMAIL and not details["identity_email"] and "identity_email" not in errors:
        errors["identity_email"] = "report.error_need_email"
    if details["consent_contact"] and preference == CONTACT_TRACKING:
        details["consent_contact"] = ""
    return details, errors


def first_incomplete(values: Mapping[str, Any]) -> int | None:
    """The first step whose required answers are missing, or None when the report can be submitted."""
    if values.get("category") not in P.CATEGORIES:
        return 1
    if values.get("immediate_danger") not in (DANGER_YES, DANGER_NO, DANGER_UNSURE):
        return 2
    if len(str(values.get("narrative") or "")) < 10:
        return 3
    if values.get("submission_type") not in (SUBMISSION_ANONYMOUS, SUBMISSION_CONFIDENTIAL):
        return 4
    if values.get("consent_process") != "y":
        return 6
    return None


def case_data(values: Mapping[str, Any]) -> dict[str, Any]:
    """Translate saved step answers into the input the case service expects."""
    category = values["category"]
    return {
        "category": category,
        "title": CATEGORY_TITLES.get(category, "Report"),
        "narrative": values["narrative"],
        "approximate_time": values.get("approximate_time", ""),
        "location_text": values.get("location_text", ""),
        "immediate_danger": values.get("immediate_danger", DANGER_UNSURE),
        "child_involved": values.get("child_involved") == "y" or category == "child_safety",
        "submission_type": values["submission_type"],
        "consent_process": values.get("consent_process") == "y",
        "consent_publication": values.get("consent_publication") == "y",
        "consent_contact": values.get("consent_contact") == "y",
        "contact_preference": values.get("contact_preference", CONTACT_TRACKING),
        "identity_name": values.get("identity_name", ""),
        "identity_phone": values.get("identity_phone", ""),
        "identity_email": values.get("identity_email", ""),
        "safe_contact_notes": values.get("safe_contact_notes", ""),
        "do_not_contact": values.get("do_not_contact", ""),
        "safe_hours": values.get("safe_hours", ""),
    }
