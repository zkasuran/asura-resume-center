"""Asura Resume Center — the server.

ONE FastAPI process (loopback-only) that serves:
  * /api/sessions — the unified, folder-grouped resume view (live from the store)
  * /api/sync     — force a rebuild of the store from disk, return fresh view
  * /api/stats    — counts only
  * /             — the single 9router-style web dashboard

The dashboard reads /api/sessions on an interval, so it stays synced with
whatever the bridge/watcher has written to the store.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

import reaper
import store

APP_NAME = "Asura Resume Center"
APP_TAG = "every CLI session — resume commands, grouped by project folder"
LISTEN_HOST = os.environ.get("ARC_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("ARC_PORT", "8791"))

app = FastAPI(title=APP_NAME)


@app.get("/api/stats")
async def api_stats():
    snap = store.load()
    return JSONResponse({"app": APP_NAME, "tag": APP_TAG, **snap.get("stats", {}),
                         "generated_at": snap.get("generated_at", "")})


@app.get("/api/sessions")
async def api_sessions():
    """The live view: always reads the store (which reflects the latest sync)."""
    return JSONResponse(store.load())


@app.post("/api/sync")
async def api_sync():
    """Force a rebuild from disk, then return the fresh view."""
    return JSONResponse(store.sync())


# --------------------------------------------------------------------------- #
# Free memory (destructive — guarded)
# --------------------------------------------------------------------------- #
@app.get("/api/reap")
async def api_reap_list():
    """Enumerate deletable artifacts (sessions / memory / projects) with sizes."""
    return JSONResponse(reaper.enumerate_all())


@app.post("/api/reap")
async def api_reap_delete(request: Request):
    """Delete a selected set. body: {ids: [...], dry_run?: bool}.

    After a real delete, the sync store is rebuilt so the dashboard stays
    accurate. This is destructive and not reversible.
    """
    body = await request.json()
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return JSONResponse(status_code=400, content={"error": "ids must be a list of strings"})
    dry = bool(body.get("dry_run", False))
    include_wf = bool(body.get("include_worked_folders", False))
    result = reaper.delete(ids, dry_run=dry, include_worked_folders=include_wf)
    if not dry:
        store.sync()  # keep the resume view in sync with disk
    return JSONResponse(result)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    try:
        from dashboard_ui import DASHBOARD_HTML
    except Exception as e:  # pragma: no cover
        return HTMLResponse(f"<h1>{APP_NAME}</h1><p>dashboard not available: {e}</p>")
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


def main():
    import uvicorn

    snap = store.load()
    s = snap.get("stats", {})
    print(f"{APP_NAME} on http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"  Dashboard : http://{LISTEN_HOST}:{LISTEN_PORT}/")
    print(f"  Sessions  : {s.get('total', 0)} total · {s.get('kiro', 0)} kiro-cli · "
          f"{s.get('claude', 0)} claude · {s.get('folders', 0)} folders")
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT, log_level="warning")


if __name__ == "__main__":
    main()
