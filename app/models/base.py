from __future__ import annotations

import secrets
from datetime import UTC, datetime

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def random_reference(prefix: str = "HL") -> str:
    """Public case reference, e.g. HL-7F3K-9Q2M (40 bits of entropy, no ambiguous letters)."""
    chars = "".join(secrets.choice(CROCKFORD) for _ in range(8))
    return f"{prefix}-{chars[:4]}-{chars[4:]}"


def random_secret(length: int = 14) -> str:
    return "".join(secrets.choice(CROCKFORD) for _ in range(length))
