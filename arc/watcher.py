"""Asura Resume Center — the bridge watcher (the "plugin").

This is the active half of the bridge: it rebuilds the sync store from disk on
a fixed interval so the dashboard always reflects new/updated sessions from
both kiro-cli and Claude Code without any manual action. The server reads the
same store, so the dashboard is continuously in sync.

Run via `arc watch` (foreground) or as the systemd user service `arc-watch`.
"""

from __future__ import annotations

import os
import time

import store

INTERVAL = int(os.environ.get("ARC_WATCH_INTERVAL", "4"))


def run_forever(interval: int = INTERVAL) -> None:
    print(f"arc bridge watcher: syncing every {interval}s -> {store.store_path()}")
    while True:
        try:
            snap = store.sync()
            s = snap.get("stats", {})
            print(f"  synced {s.get('total', 0)} sessions "
                  f"({s.get('kiro', 0)} kiro · {s.get('claude', 0)} claude) "
                  f"across {s.get('folders', 0)} folders", flush=True)
        except Exception as e:  # keep the watcher alive
            print(f"  sync error: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
