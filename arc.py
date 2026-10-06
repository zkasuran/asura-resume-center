#!/usr/bin/env python3
"""arc — Asura Resume Center launcher & CLI.

Running `arc` with no arguments opens the web dashboard (starting the server
if needed). Use `arc -h` for this help.

Server / dashboard (9router-style, loopback-only):
  arc web                 open the dashboard in your browser (prints URL)
  arc start | stop | restart | status | logs
  arc serve               run the server in the foreground

Bridge / sync:
  arc sync                rebuild the store from disk once (both CLIs)
  arc watch               run the bridge watcher in the foreground
  arc watch-start | watch-stop | watch-status   (systemd user service)

Inspect:
  arc list [filter]       print every resume target (folder · CLI · command)
  arc stats               counts

Free memory:
  arc reap [sessions|memory|projects]   list deletable artifacts + sizes
                                        (delete via the dashboard's checkbox UI)

The bridge collects resume commands for BOTH kiro-cli and Claude Code, keyed by
the working folder each session ran in, and keeps the dashboard synced.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(APP_ROOT, "arc")
VENV_PY = os.path.join(APP_ROOT, ".venv", "bin", "python")
SERVICE = "arc.service"
WATCH_SERVICE = "arc-watch.service"
HOST = os.environ.get("ARC_HOST", "127.0.0.1")
PORT = os.environ.get("ARC_PORT", "8791")
BASE = f"http://{HOST}:{PORT}"


def _py():
    return VENV_PY if os.path.exists(VENV_PY) else sys.executable


def _env():
    return dict(os.environ, PYTHONPATH=PKG + os.pathsep + os.environ.get("PYTHONPATH", ""))


def _run_mod(code):
    return subprocess.call([_py(), "-c", code], env=_env())


def _systemctl(*a):
    return subprocess.call(["systemctl", "--user", *a])


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def _post(path):
    req = urllib.request.Request(BASE + path, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ---- server lifecycle ----
def serve():
    return _run_mod("import server; server.main()")


def start():
    return _systemctl("start", SERVICE)


def stop():
    return _systemctl("stop", SERVICE)


def restart():
    return _systemctl("restart", SERVICE)


def logs():
    return _systemctl("--no-pager", "status", SERVICE)


def status():
    rc = _systemctl("is-active", SERVICE)
    try:
        s = _get("/api/stats")
        print(f"server    : active on {BASE}")
        print(f"dashboard : {BASE}/")
        print(f"sessions  : {s.get('total', 0)} total · {s.get('kiro', 0)} kiro-cli · "
              f"{s.get('claude', 0)} claude · {s.get('folders', 0)} folders")
        print(f"last sync : {s.get('generated_at', '?')}")
    except Exception as e:
        print(f"server    : not reachable at {BASE} ({type(e).__name__}) — try `arc start`")
    wrc = subprocess.run(["systemctl", "--user", "is-active", WATCH_SERVICE],
                         capture_output=True, text=True).stdout.strip()
    print(f"watcher   : {wrc or 'unknown'}")
    return rc


def _server_up(timeout=1.5):
    try:
        with urllib.request.urlopen(BASE + "/healthz", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server(wait=8.0):
    """Make sure the server is reachable; start the services if not."""
    if _server_up():
        return True
    # try the managed services first, fall back to a detached serve
    subprocess.call(["systemctl", "--user", "start", SERVICE, WATCH_SERVICE])
    import time
    deadline = time.time() + wait
    while time.time() < deadline:
        if _server_up():
            return True
        time.sleep(0.4)
    # last resort: spawn a detached foreground server
    try:
        subprocess.Popen([_py(), "-c", "import server; server.main()"], env=_env(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass
    deadline = time.time() + wait
    while time.time() < deadline:
        if _server_up():
            return True
        time.sleep(0.4)
    return _server_up()


def web():
    if not _ensure_server():
        print(f"could not reach the server at {BASE} — try `arc start` and check `arc logs`")
        return 1
    print(BASE + "/")
    from shutil import which
    for o in ("xdg-open", "gio", "sensible-browser", "x-www-browser"):
        if which(o):
            try:
                subprocess.Popen([o, "open", BASE + "/"] if o == "gio" else [o, BASE + "/"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
            except Exception:
                continue
    return 0


# ---- bridge / sync ----
def sync():
    sys.path.insert(0, PKG)
    import store  # noqa
    snap = store.sync()
    s = snap["stats"]
    print(f"synced {s['total']} sessions ({s['kiro']} kiro-cli · {s['claude']} claude) "
          f"across {s['folders']} folders -> {store.store_path()}")
    return 0


def watch():
    return _run_mod("import watcher; watcher.run_forever()")


def watch_start():
    return _systemctl("start", WATCH_SERVICE)


def watch_stop():
    return _systemctl("stop", WATCH_SERVICE)


def watch_status():
    return _systemctl("--no-pager", "status", WATCH_SERVICE)


# ---- inspect (read the store directly; no server needed) ----
def _load_store():
    sys.path.insert(0, PKG)
    import store  # noqa
    return store.load()


def cmd_list(args):
    filt = (args[0].lower() if args and not args[0].startswith("-") else "")
    snap = _load_store()
    n = 0
    for g in snap.get("groups", []):
        shown = [s for s in g["sessions"]
                 if not filt or filt in (s["title"] + " " + s["cli"] + " " +
                                         g["folder"] + " " + s["resume_command"]).lower()]
        if not shown:
            continue
        print(f"\n\033[1m{g['name']}\033[0m  \033[90m{g['folder']}\033[0m  "
              f"({g['kiro']} kiro · {g['claude']} claude)")
        for s in shown:
            tag = "kiro-cli" if s["cli"] == "kiro-cli" else "claude  "
            print(f"  [{tag}] {s['title'][:60]:<60}")
            print(f"            {s['resume_command']}")
            n += 1
    st = snap.get("stats", {})
    print(f"\n-- {n} shown · {st.get('total', 0)} total "
          f"({st.get('kiro', 0)} kiro-cli · {st.get('claude', 0)} claude) "
          f"across {st.get('folders', 0)} folders")
    return 0


def cmd_stats(_):
    snap = _load_store()
    print(json.dumps({**snap.get("stats", {}), "generated_at": snap.get("generated_at", "")}, indent=2))
    return 0


def cmd_reap(args):
    """arc reap [sessions|memory|projects]  — list deletable artifacts + sizes.

    Deletion from the CLI is intentionally dry-run only; use the dashboard's
    checkbox + confirm flow to actually delete.
    """
    sys.path.insert(0, PKG)
    import reaper  # noqa
    data = reaper.enumerate_all()
    cat = args[0] if args and args[0] in ("sessions", "memory", "projects") else None
    cats = [cat] if cat else ["sessions", "memory", "projects"]
    for c in cats:
        t = data["totals"][c]
        print(f"\n\033[1m{c}\033[0m — {t['count']} items · {t['human']}")
        for a in data[c][:15]:
            tag = (a["cli"] or "")[:8]
            print(f"  {a['human']:>9}  [{tag:<8}] {a['label'][:52]:<52}")
        if len(data[c]) > 15:
            print(f"  … and {len(data[c]) - 15} more")
    g = data["totals"]
    grand = g["sessions"]["bytes"] + g["memory"]["bytes"] + g["projects"]["bytes"]
    print(f"\n-- reclaimable: {reaper.human(grand)} "
          f"(sessions {g['sessions']['human']} · memory {g['memory']['human']} · projects {g['projects']['human']})")
    print("   delete via the dashboard: arc web  →  🗑 Free memory")
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if not argv:
        # bare `arc` opens the dashboard (ensuring the server is up first)
        return web()
    v, rest = argv[0], argv[1:]
    simple = {
        "serve": serve, "start": start, "stop": stop, "restart": restart,
        "logs": logs, "status": status, "web": web,
        "sync": sync, "watch": watch,
        "watch-start": watch_start, "watch-stop": watch_stop, "watch-status": watch_status,
    }
    if v in simple:
        return simple[v]()
    if v == "list":
        return cmd_list(rest)
    if v == "stats":
        return cmd_stats(rest)
    if v == "reap":
        return cmd_reap(rest)
    print(f"unknown command {v!r}\n")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
