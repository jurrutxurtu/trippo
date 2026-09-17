"""Generate `docs/technical/data-model.md` and `capsule.schema.json` from the Pydantic models.

The spec cannot drift from the code, because the spec IS the code. `just check` runs this
with `--check` and fails if regenerating would change anything.

Never hand-edit the generated files. AGENTS.md section 3.4.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trippo.domain.models import SCHEMA_VERSION, Trip

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "technical" / "data-model.md"
SCHEMA = ROOT / "docs" / "technical" / "capsule.schema.json"

HEADER = f"""<!-- GENERATED FILE -- DO NOT EDIT BY HAND.
     Regenerate with `just gen-docs`. Source of truth: backend/trippo/domain/models.py -->

# Data model (generated)

Capsule schema version **{SCHEMA_VERSION}**.

This document is generated from the Pydantic models in `backend/trippo/domain/models.py`.
For the prose contract -- layout on disk, portability rules, invariants and migrations --
see [`capsule-format.md`](capsule-format.md).

"""


def build_schema() -> dict:
    return Trip.model_json_schema(mode="serialization")


def render(schema: dict) -> str:
    out = [HEADER]
    defs = schema.get("$defs", {})

    out.append("## Entities\n")
    out.append("| Model | Fields | Description |\n| --- | --- | --- |")
    for name in sorted(defs):
        d = defs[name]
        if d.get("enum"):
            continue
        props = d.get("properties", {})
        desc = (d.get("description") or "").strip().split("\n")[0]
        out.append(f"| `{name}` | {len(props)} | {desc} |")
    out.append("")

    out.append("## Enumerations\n")
    for name in sorted(defs):
        d = defs[name]
        if not d.get("enum"):
            continue
        values = ", ".join(f"`{v}`" for v in d["enum"])
        out.append(f"- **{name}**: {values}")
    out.append("")

    out.append("## Fields\n")
    for name in sorted(defs):
        d = defs[name]
        if d.get("enum"):
            continue
        out.append(f"### {name}\n")
        if d.get("description"):
            out.append(d["description"].strip() + "\n")
        props = d.get("properties", {})
        if not props:
            out.append("_No fields._\n")
            continue
        required = set(d.get("required", []))
        out.append("| Field | Type | Required | Notes |")
        out.append("| --- | --- | --- | --- |")
        for field, spec in props.items():
            out.append(
                f"| `{field}` | {_type_of(spec)} | "
                f"{'yes' if field in required else 'no'} | "
                f"{_first_line(spec)} |"
            )
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _first_line(spec: dict) -> str:
    desc = (spec.get("description") or "").strip()
    return desc.splitlines()[0] if desc else ""


def _type_of(spec: dict) -> str:
    if "$ref" in spec:
        return f"`{spec['$ref'].rsplit('/', 1)[-1]}`"
    if "anyOf" in spec:
        return " \\| ".join(_type_of(s) for s in spec["anyOf"])
    if spec.get("type") == "array":
        return f"array of {_type_of(spec.get('items', {}))}"
    if "type" in spec:
        return f"`{spec['type']}`"
    return "`any`"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if the generated files are stale")
    args = ap.parse_args()

    schema = build_schema()
    schema_text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    doc_text = render(schema)

    if args.check:
        stale = []
        for path, text in ((DOC, doc_text), (SCHEMA, schema_text)):
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.relative_to(ROOT).as_posix())
        if stale:
            print(
                "schema drift: the capsule models changed but the generated docs did not.\n"
                "  stale: " + ", ".join(stale) + "\n"
                "  fix:   just gen-docs   (and bump SCHEMA_VERSION + add a migration if "
                "the capsule format itself changed -- AGENTS.md section 3.6)",
                file=sys.stderr,
            )
            return 1
        print("schema docs are up to date")
        return 0

    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(doc_text, encoding="utf-8")
    SCHEMA.write_text(schema_text, encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)} and {SCHEMA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
