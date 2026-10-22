# Help Lagbe?

Secular human-support and public-accountability platform.

## Run locally
```bash
pip install -r requirements.txt
python run.py
```

Demo accounts (local only):
- admin@helplagbe.local / admin123
- support@helplagbe.local / support123
- legal@helplagbe.local / legal123
- cyber@helplagbe.local / cyber123
- editor@helplagbe.local / editor123
- user@helplagbe.local / user123

## Features
- Role-based auth
- Anonymous complaint submission
- Private case management with action tracking
- Editorial approval with identity redaction
- Access logging for sensitive views
- Public publication of redacted reports

## Security
- Identities never exposed publicly by default
- Passwords hashed with bcrypt
- Access to non-anonymous data is logged
- Do not deploy with default SECRET_KEY
