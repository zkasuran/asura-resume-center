"""Asura Resume Center — the sync store (the bridge's persistence).

`arc sync` (and the background watcher) write a snapshot here; the server reads
it live on every request so the dashboard is always in sync with disk. The
store is a single JSON file written atomically.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from collector import snapshot

APP_DIR = Path(os.path.expanduser("~")) / ".local" / "share" / "arc"
STORE = APP_DIR / "store.json"


def _ensure_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def sync() -> dict:
    """Rebuild the snapshot from disk and persist it atomically. Returns it."""
    _ensure_dir()
    snap = snapshot()
    snap["synced_ts"] = time.time()
    fd, tmp = tempfile.mkstemp(dir=str(APP_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, indent=2)
        os.replace(tmp, STORE)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return snap


def load(auto_sync: bool = True) -> dict:
    """Load the persisted snapshot. If missing/stale, rebuild it first."""
    if not STORE.exists():
        return sync() if auto_sync else {"groups": [], "stats": {}, "generated_at": ""}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return sync() if auto_sync else {"groups": [], "stats": {}, "generated_at": ""}


def store_path() -> str:
    return str(STORE)


if __name__ == "__main__":
    s = sync()
    print(f"synced {s['stats']['total']} sessions across {s['stats']['folders']} folders -> {STORE}")
