"""Storage port -- the only abstraction over the filesystem. ADR-0001.

`LocalFsStorage` is the sole implementation in the POC. An `S3Storage` would be roughly
a hundred lines, which is exactly the point: the migration to a hosted product must not
require touching the domain or the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    """Capsule-relative I/O. Keys are POSIX-style relative paths, never absolute."""

    def read_bytes(self, key: str) -> bytes: ...
    def write_bytes(self, key: str, data: bytes) -> None: ...
    def read_text(self, key: str) -> str: ...
    def write_text(self, key: str, text: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str) -> list[str]: ...
    def delete(self, key: str) -> None: ...


class LocalFsStorage:
    """Filesystem-backed storage rooted at a capsule directory.

    This is the ONLY place allowed to turn a capsule key into an absolute path.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if key.startswith(("/", "\\")) or (len(key) > 1 and key[1] == ":"):
            raise ValueError(f"storage keys must be relative, got {key!r}")
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError(f"storage key escapes the capsule root: {key!r}")
        return p

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read_text(self, key: str) -> str:
        return self._path(key).read_text(encoding="utf-8")

    def write_text(self, key: str, text: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()
