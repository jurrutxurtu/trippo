# Trippo task runner.  https://github.com/casey/just
# Every recipe assumes the backend venv at backend/.venv (created by `just setup`).

py := "backend/.venv/Scripts/python.exe"

default:
    @just --list

# Create the virtualenv and install dependencies (Python 3.12 via uv).
setup:
    cd backend && python -m uv venv --python 3.12
    cd backend && python -m uv pip install --python .venv/Scripts/python.exe -e ".[dev]"

# Everything that must pass before work is considered done. AGENTS.md section 3.7.
check: lint types test gen-docs-check
    @echo "all checks passed"

lint:
    cd backend && .venv/Scripts/python.exe -m ruff check trippo tests scripts

fmt:
    cd backend && .venv/Scripts/python.exe -m ruff format trippo tests scripts
    cd backend && .venv/Scripts/python.exe -m ruff check --fix trippo tests scripts

types:
    cd backend && .venv/Scripts/python.exe -m mypy trippo

test:
    cd backend && .venv/Scripts/python.exe -m pytest

# Golden snapshots only -- the real-data regression suite.
golden:
    cd backend && .venv/Scripts/python.exe -m pytest tests/golden -v

# Regenerate data-model.md + capsule.schema.json from the Pydantic models.
gen-docs:
    cd backend && .venv/Scripts/python.exe scripts/gen_schema_docs.py

# Fail if the generated docs are stale. Part of `just check`.
gen-docs-check:
    cd backend && .venv/Scripts/python.exe scripts/gen_schema_docs.py --check

# Build a draft capsule. Every source is optional.
#   just build --timeline T.json --gpx tracks/ --media photos/ --from 2023-09-20 --to 2023-10-16
build *ARGS:
    cd backend && .venv/Scripts/python.exe -m trippo.cli build {{ARGS}}

# Regenerate the redacted golden fixture from a real export.
fixture timeline gpx:
    cd backend && .venv/Scripts/python.exe scripts/make_fixture.py \
        --timeline "{{timeline}}" --gpx "{{gpx}}" --out ../fixtures/golden/ireland-2023
