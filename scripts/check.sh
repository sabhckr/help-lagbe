#!/usr/bin/env bash
# Runs the full verification suite: lint, types, security scan, dependency audit, tests, production build check.
set -u
cd "$(dirname "$0")/.."
if [ -d .venv ]; then . .venv/bin/activate; fi
status=0
run() { echo; echo "== $1"; shift; "$@" || { echo "-- FAILED: $*"; status=1; }; }
run "ruff (lint)"            ruff check app config.py run.py wsgi.py tests
run "ruff (format check)"    ruff format --check app config.py run.py wsgi.py tests
run "mypy (types)"           mypy app config.py
run "bandit (security)"      bandit -q -c pyproject.toml -r app config.py
run "pip-audit (dependencies)" pip-audit -r requirements.txt
run "pytest"                 python -m pytest
run "compileall (build)"     python -m compileall -q app config.py run.py wsgi.py
run "template compile"       python -c "from app import create_app; a=create_app('testing'); [a.jinja_env.get_template(t) for t in a.jinja_env.list_templates()]; print('templates OK')"
run "production config check" env APP_ENV=production SECRET_KEY=0123456789abcdef0123456789abcdef0123456789 IDENTITY_ENCRYPTION_KEY=u0kG8s7Q4N4x5cQ1yq1vF1n0q3M5s7f9r2t4y6u8i0o= DATABASE_URL=sqlite:///instance/prod-check.db RATELIMIT_STORAGE_URI=redis://localhost:6379/1 python -c "from config import ProductionConfig as P; P.validate(); print('production config OK')"
echo; if [ $status -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED"; fi
exit $status
