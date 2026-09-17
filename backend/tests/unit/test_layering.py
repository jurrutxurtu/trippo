"""The layering rule is enforced, not merely documented. AGENTS.md section 2.

`domain/` is pure: no I/O, no filesystem, no network, no dependency on outer layers.
That purity is what makes the draft pipeline testable without fixtures on disk, and what
would let the same code run server-side if the hosted viewer is ever built (ADR-0001).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
DOMAIN = BACKEND / "trippo" / "domain"

FORBIDDEN_MODULES = {
    "pathlib",
    "os",
    "io",
    "shutil",
    "httpx",
    "requests",
    "sqlite3",
    "open",
    "socket",
    "subprocess",
}
FORBIDDEN_PACKAGES = {
    "trippo.api",
    "trippo.ingest",
    "trippo.draft",
    "trippo.enrich",
    "trippo.ai",
    "trippo.capsule",
    "trippo.ports",
    "trippo.observe",
}


def _domain_files() -> list[Path]:
    return sorted(p for p in DOMAIN.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("path", _domain_files(), ids=lambda p: p.name)
def test_domain_is_pure(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in FORBIDDEN_MODULES, (
                    f"{path.name} imports {alias.name}: domain must stay I/O-free"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in FORBIDDEN_MODULES, (
                f"{path.name} imports from {node.module}: domain must stay I/O-free"
            )
            for pkg in FORBIDDEN_PACKAGES:
                assert not node.module.startswith(pkg), (
                    f"{path.name} imports {node.module}: domain must not depend on an outer layer"
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open", f"{path.name} calls open(): domain must be pure"


def test_heuristics_are_centralised() -> None:
    """No magic numbers outside config/heuristics.py. AGENTS.md section 3.5.

    A crude but effective guard: flag float literals in the draft pipeline, where every
    threshold should be a named import.
    """
    allowed = {0.0, 1.0, 0.5, 2.0, 60.0, 100.0, 1000.0, 3600.0, 3.6, 0.1, 0.01, 24.0, 250.0}
    offenders: list[str] = []
    for path in sorted((BACKEND / "trippo" / "draft").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, float)
                and node.value not in allowed
            ):
                offenders.append(f"{path.name}:{node.lineno} -> {node.value}")
    assert not offenders, (
        "unnamed numeric thresholds found; move them to config/heuristics.py and "
        "document them in docs/technical/heuristics-tunables.md:\n  " + "\n  ".join(offenders)
    )
