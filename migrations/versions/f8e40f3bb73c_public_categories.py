"""Public category keys.

Maps the earlier fifteen internal category keys onto the eight plain-language categories shown
to reporters. Rows that already use a new key are untouched. The downgrade cannot restore the
original fine-grained keys, so it is a no-op.
"""
from alembic import op

revision = "f8e40f3bb73c"
down_revision = "ad98f3ba2125"
branch_labels = None
depends_on = None

MAPPING = {
    "bullying": "harassment",
    "eve_teasing": "harassment",
    "sexual_harassment": "harassment",
    "blackmail": "threats_blackmail",
    "threats": "threats_blackmail",
    "domestic_violence": "abuse_violence",
    "bribery": "corruption_exploitation",
    "corruption": "corruption_exploitation",
    "exploitation": "corruption_exploitation",
    "cyber_harassment": "online_harm",
    "account_takeover": "online_harm",
    "image_abuse": "online_harm",
    "child_abuse": "child_safety",
    "legal_question": "other",
}


def upgrade():
    for old, new in MAPPING.items():
        op.execute(f"UPDATE cases SET category = '{new}' WHERE category = '{old}'")


def downgrade():
    pass
