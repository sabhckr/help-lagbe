"""Heuristic identifier scan used as a hard gate before publication. It cannot prove a text is
safe; it only refuses obvious leaks so a human must look again."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<!\d)(?:\+?88)?0?1[3-9]\d{8}(?!\d)"),  # Bangladeshi mobile numbers
    "phone_generic": re.compile(r"(?<!\d)(?:\+?\d[\d \-()]{8,}\d)(?!\d)"),
    "nid": re.compile(r"(?<!\d)(?:\d{10}|\d{13}|\d{17})(?!\d)"),  # NID formats
    "url": re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE),
    "handle": re.compile(r"(?<!\w)@[A-Za-z0-9_.]{3,}"),
    "bn_phone": re.compile(r"[০-৯]{11}"),
}
_SENSITIVE_WORDS = re.compile(
    r"\b(nid|passport|birth certificate|home address|house no|flat no|জাতীয় পরিচয়|পাসপোর্ট|বাসা নং|ঠিকানা)\b",
    re.IGNORECASE,
)


@dataclass
class Finding:
    kind: str
    sample: str


def scan_for_identifiers(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for kind, pattern in _PATTERNS.items():
        for m in pattern.finditer(text or ""):
            sample = m.group(0)
            findings.append(Finding(kind=kind, sample=sample[:6] + "…" if len(sample) > 8 else sample))
    for m in _SENSITIVE_WORDS.finditer(text or ""):
        findings.append(Finding(kind="sensitive_term", sample=m.group(0)))
    return findings


REDACTION_CHECKLIST = (
    "no_names",
    "no_contacts",
    "no_addresses",
    "no_documents",
    "no_images_of_people",
    "no_child_identifiers",
    "allegation_language",
)
