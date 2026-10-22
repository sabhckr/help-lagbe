"""Regenerate docs/PERMISSIONS.md from app/permissions.py so the document cannot drift from the code."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import permissions as P  # noqa: E402

ROLE_TITLES = {
    "admin": "Admin & Governance", "legal": "Law & Legal", "cyber": "Cyber & Forensics", "support": "Human Support",
    "supervisor": "Safeguarding Supervisor", "editorial": "Investigations & Editorial", "action": "Action & Response", "moderator": "Moderation",
}


def build() -> str:
    roles = list(P.STAFF_ROLES)
    lines = [
        "# Role and permission matrix", "",
        "Generated from `app/permissions.py` (run `python scripts/gen_permissions_doc.py` after changing it). Permissions are fixed per role in code; there is no per-user permission editing. **Case content is additionally need-to-know**: holding `case.view_narrative` only lets you read cases you are assigned to, cases in your own department that are still in intake (submitted/triage), or, for the safeguarding supervisor, cases of the support department. Administrators never read narratives, identities or support chats except through logged break-glass access.",
        "", "## Roles", "",
    ]
    lines += [f"- **{r}** — {ROLE_TITLES[r]} (department: `{P.ROLE_DEPARTMENT[r]}`)" for r in roles]
    lines.append("- **reporter** — public account; no workspace permissions at all.")
    header = "| " + " | ".join(roles) + " |"
    sep = "|---|" + "---|" * len(roles)
    lines += ["", "## Sensitive actions", "", "| Action " + header, sep]
    for perm, label in P.SENSITIVE_ACTIONS:
        lines.append(f"| {label} (`{perm}`) | " + " | ".join("✓" if perm in P.ROLE_PERMISSIONS[r] else "" for r in roles) + " |")
    lines += ["", "## Full matrix", "", "| Permission " + header, sep]
    for perm in sorted(P.ALL_PERMISSIONS):
        lines.append(f"| `{perm}` | " + " | ".join("✓" if perm in P.ROLE_PERMISSIONS[r] else "" for r in roles) + " |")
    lines += ["", "## Case routing by category", "", "| Category | First department |", "|---|---|"]
    lines += [f"| `{cat}` | {dept} |" for cat, dept in P.CATEGORY_DEPARTMENT.items()]
    lines += [
        "", "## Reason-gated, logged actions", "",
        "The following always require a written reason and write an `AuditEvent` (actor, role, time, case, reason, hashed IP):", "",
        "- Unlocking a reporter identity (`identity.unlock`; refused attempts are logged as `identity.unlock_refused`).",
        "- Downloading or exporting evidence (`evidence.download`, `evidence.export`; refusals logged).",
        "- Administrator break-glass reads (`case.break_glass`).",
        "- Supervisor reads of support conversations they are not part of (`support.supervisor_read`).",
        "- Audit-trail export (`audit.export`).",
        "- Identity purge under retention (`identity.purge`).",
        "- Role changes and MFA resets (`admin.role_changed`, `admin.mfa_reset`).", "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    (ROOT / "docs" / "PERMISSIONS.md").write_text(build())
    print("docs/PERMISSIONS.md regenerated")
