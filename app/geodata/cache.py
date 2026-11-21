"""Small file cache: one JSON (or binary) file per request key, safe on Windows and Linux."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from . import config
from .errors import CacheMiss

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(key: str) -> str:
    """File-system safe name: readable prefix plus a hash of the full key."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"{_SAFE.sub('_', key)[:60].strip('._')}-{digest}"


def path_for(namespace: str, key: str, suffix: str = ".json") -> Path:
    return config.cache_dir() / namespace / (_slug(key) + suffix)


def _fresh(path: Path, ttl: float | None) -> bool:
    if not path.is_file():
        return False
    return ttl is None or (time.time() - path.stat().st_mtime) < ttl


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # atomic on both POSIX and Windows


def get_json(namespace: str, key: str, ttl: float | None = None) -> Any | None:
    """Return the cached value or None. In offline mode stale entries are served too."""
    path = path_for(namespace, key)
    if not _fresh(path, None if config.is_offline() else ttl):
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def put_json(namespace: str, key: str, value: Any) -> None:
    _atomic_write(path_for(namespace, key), json.dumps(value, ensure_ascii=False).encode("utf-8"))


def get_bytes(namespace: str, key: str, ttl: float | None = None, suffix: str = ".bin") -> bytes | None:
    path = path_for(namespace, key, suffix)
    if not _fresh(path, None if config.is_offline() else ttl):
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def put_bytes(namespace: str, key: str, value: bytes, suffix: str = ".bin") -> None:
    _atomic_write(path_for(namespace, key, suffix), value)


def require_online(namespace: str, key: str) -> None:
    """Call right before any network request: raises CacheMiss in offline mode."""
    if config.is_offline():
        raise CacheMiss(f"offline: no cached entry for {namespace}:{key}")
