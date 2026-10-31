"""Small deterministic, atomic serialization and fingerprint helpers."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tree_hash(root: Path, *, suffixes: set[str] | None = None) -> str:
    h = hashlib.sha256()
    paths = sorted(p for p in root.rglob("*") if p.is_file()
                   and not {".git", "__pycache__"}.intersection(p.parts)
                   and (suffixes is None or p.suffix in suffixes))
    if not paths:
        raise ValueError(f"no fingerprintable files in {root}")
    for path in paths:
        h.update(path.relative_to(root).as_posix().encode() + b"\0")
        h.update(bytes.fromhex(file_hash(path)))
    return h.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"missing or repeated CSV columns: {path}")
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError(f"ragged CSV rows: {path}")
        return [{k: v.strip() for k, v in row.items()} for row in rows]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    import io
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: canonical(v) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()})
    atomic_text(path, stream.getvalue())
