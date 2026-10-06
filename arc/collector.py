"""Asura Resume Center — the collector / bridge.

Walks the on-disk session stores of both supported CLIs and produces a single
unified list of *resume targets*, each keyed by the working folder it ran in:

  * kiro-cli : ~/.kiro/sessions/cli/<uuid>.json
               -> resume with `kiro-cli chat --resume-id <uuid>`
               (resume is also directory-scoped, so we record the cwd)

  * Claude Code : ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl
               -> resume with `claude --resume <uuid>`
               (must be launched from the project's cwd)

The collector only *reads*. It never mutates a session file. The bridge
(arc.store) is what persists the unified view the dashboard reads.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

HOME = Path(os.path.expanduser("~"))
KIRO_SESSIONS = HOME / ".kiro" / "sessions" / "cli"
CLAUDE_PROJECTS = HOME / ".claude" / "projects"


# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
@dataclass
class ResumeTarget:
    """One resumable conversation, with the exact command to continue it."""

    cli: str              # "kiro-cli" | "claude"
    session_id: str
    folder: str           # the primary worked-on folder (inferred), else launch cwd
    worked_folders: list  # ALL significant worked-on folders, most-worked first
    launch_cwd: str       # the cwd the CLI was launched in
    worked_inferred: bool # True if `folder` came from transcript analysis
    title: str            # human label (ai/title or first prompt)
    updated_at: str       # ISO-8601 UTC, best-effort
    updated_ts: float     # epoch seconds for sorting
    resume_command: str   # click-to-copy, ready to paste

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return ""


def _parse_iso(s: str) -> float:
    """Parse an ISO-8601 string (optionally Z-suffixed) into epoch seconds."""
    if not s:
        return 0.0
    try:
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2).timestamp()
    except Exception:
        return 0.0


def _shq(path: str) -> str:
    """Single-quote a path for safe shell pasting."""
    return "'" + path.replace("'", "'\\''") + "'"


def _clip(text: str, n: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# --------------------------------------------------------------------------- #
# worked-folder inference
#
# The CLI's launch cwd is often just ~ ; what the user cares about is the
# project the session actually *worked on*. We infer it from the absolute paths
# that appear in tool-use inputs (edited/read files, shell commands, working
# dirs) across the transcript, then pick the most-referenced meaningful dir.
# --------------------------------------------------------------------------- #
import re as _re

_HOME_STR = str(HOME)
# directories that are noise, never the "project" a session worked on
_IGNORE_SEGMENTS = (
    "/.kiro/", "/.claude/", "/.nvm/", "/.venv/", "/venv/", "/node_modules/",
    "/.cache/", "/.git/", "/__pycache__/", "/.local/share/arc/", "/site-packages/",
    "/.config/", "/.npm/", "/claude-1000/", "/tool-results/", "/subagents/",
    "/.local/bin/", "/.local/state/",
)
# scratch/system roots that only count weakly (never beat a real project dir)
_WEAK_PREFIXES = ("/tmp", "/var", "/opt", "/srv")
_PATH_RE = _re.compile(r"/(?:home/[\w.\-]+|root|tmp|opt|srv|var)[\w./\-]*")


def _candidate_dirs_from_text(text: str) -> list[str]:
    """Pull absolute paths out of a string and return their directories."""
    out = []
    for m in _PATH_RE.findall(text or ""):
        # strip a trailing filename if it looks like a file (has an extension)
        p = m.rstrip("/")
        base = os.path.basename(p)
        d = os.path.dirname(p) if ("." in base and "/" in p) else p
        if d and d != "/":
            out.append(d)
    return out


def _project_root(path: str) -> str:
    """Collapse a deep path to a stable project root under a known base.

    Keeps up to two segments beneath a recognised workspace base (e.g.
    ~/Downloads/<proj> or ~/<proj>), so sibling files in a project fold to the
    same root instead of fragmenting per-subdir.
    """
    if not path.startswith(_HOME_STR):
        return path
    rest = path[len(_HOME_STR):].strip("/")
    if not rest:
        return _HOME_STR
    parts = rest.split("/")
    # common workspace bases: Downloads, Documents, projects, work, src, dev, repos
    bases = {"Downloads", "Documents", "projects", "work", "src", "dev", "repos", "code"}
    if parts[0] in bases and len(parts) >= 2:
        keep = parts[:2]
    else:
        keep = parts[:1]
    return _HOME_STR + "/" + "/".join(keep)


def _infer_worked_folders(texts, launch_cwd: str) -> list[str]:
    """Infer ALL significant worked-on folders from tool-input strings.

    Returns a list of project roots ordered by how much the session touched
    them (most-worked first). A session commonly spans several projects, so we
    keep every folder with a real signal, not just the top one. Real project
    dirs under $HOME outrank scratch/system dirs (/tmp, /var, …).
    """
    from collections import Counter

    strong: Counter[str] = Counter()   # real project dirs
    weak: Counter[str] = Counter()     # scratch/system dirs
    lc = (launch_cwd or "").rstrip("/")
    for t in texts:
        for d in _candidate_dirs_from_text(t):
            dd = d + "/"
            if any(seg in dd for seg in _IGNORE_SEGMENTS):
                continue
            if d.startswith(_WEAK_PREFIXES):
                weak[d] += 1
                continue
            root = _project_root(d)
            if root == _HOME_STR:           # bare home = not a project
                continue
            # drop bare workspace bases (~/Downloads, ~/Documents, …) with no project under them
            _rest = root[len(_HOME_STR):].strip("/") if root.startswith(_HOME_STR) else root
            if _rest in {"Downloads", "Documents", "projects", "work", "src", "dev", "repos", "code"}:
                continue
            if root == lc:
                strong[root] += 0.25        # launch cwd itself counts weakly
            else:
                strong[root] += 1

    # keep folders with a real, repeated signal (>=2 hits), ranked.
    ranked = [f for f, n in strong.most_common() if n >= 2 and f != lc]
    if not ranked:
        # a single strong hit still beats nothing (e.g. a short session)
        singles = [f for f, n in strong.most_common() if n >= 1 and f != lc]
        ranked = singles[:1]
    if not ranked and weak:
        best, n = weak.most_common(1)[0]
        if n >= 3:
            ranked = [best]
    return ranked[:6]   # cap to keep rows tidy


def _infer_worked_folder(texts, launch_cwd: str) -> str:
    """Back-compat: the single top worked-on folder (or "")."""
    folders = _infer_worked_folders(texts, launch_cwd)
    return folders[0] if folders else ""


def _tool_input_strings_kiro(jsonl: Path, cap: int = 4000):
    """Yield path-bearing tool-input strings from a kiro .jsonl transcript."""
    keys = ("path", "file_path", "working_dir", "command", "cwd")
    n = 0
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                if n > cap:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                stack = [d]
                while stack:
                    x = stack.pop()
                    if isinstance(x, dict):
                        if x.get("kind") == "toolUse":
                            inp = (x.get("data", {}) or {}).get("input", {}) or {}
                            for k in keys:
                                v = inp.get(k)
                                if isinstance(v, str):
                                    n += 1
                                    yield v
                        else:
                            stack.extend(x.values())
                    elif isinstance(x, list):
                        stack.extend(x)
    except Exception:
        return


def _tool_input_strings_claude(jsonl: Path, cap: int = 4000):
    """Yield path-bearing tool-input strings from a Claude .jsonl transcript."""
    keys = ("file_path", "path", "command", "notebook_path", "cwd")
    n = 0
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                if n > cap:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                msg = d.get("message", {})
                cont = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(cont, list):
                    for b in cont:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            inp = b.get("input") or {}
                            for k in keys:
                                v = inp.get(k)
                                if isinstance(v, str):
                                    n += 1
                                    yield v
    except Exception:
        return


# --- inference cache (keyed by transcript path + mtime; scanning is costly) ---
_CACHE_PATH = HOME / ".local" / "share" / "arc" / "infer-cache.json"
_cache: dict | None = None


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_cache), encoding="utf-8")
    except Exception:
        pass


def _infer_cached(jsonl: Path, launch_cwd: str, which: str) -> list[str]:
    """Inference with a path+mtime cache. Returns ranked worked-on folders."""
    cache = _load_cache()
    try:
        mtime = jsonl.stat().st_mtime
    except OSError:
        return []
    key = str(jsonl)
    hit = cache.get(key)
    if hit and hit.get("mtime") == mtime and hit.get("lc") == launch_cwd and "folders" in hit:
        return hit.get("folders", [])
    gen = _tool_input_strings_kiro(jsonl) if which == "kiro" else _tool_input_strings_claude(jsonl)
    folders = _infer_worked_folders(gen, launch_cwd)
    cache[key] = {"mtime": mtime, "lc": launch_cwd, "folders": folders}
    return folders


# --------------------------------------------------------------------------- #
# kiro-cli
# --------------------------------------------------------------------------- #
def collect_kiro(root: Path = KIRO_SESSIONS) -> Iterable[ResumeTarget]:
    if not root.is_dir():
        return
    for jf in root.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        sid = data.get("session_id") or jf.stem
        launch_cwd = data.get("cwd") or ""
        title = _clip(data.get("title") or "(untitled)")
        updated = data.get("updated_at") or data.get("created_at") or ""
        ts = _parse_iso(updated)
        if not ts:
            try:
                ts = jf.stat().st_mtime
                updated = _iso(ts)
            except Exception:
                ts = 0.0
        # infer the worked-on folder(s) from the transcript (.jsonl sibling)
        jsonl = jf.with_suffix(".jsonl")
        worked_folders = _infer_cached(jsonl, launch_cwd, "kiro") if jsonl.exists() else []
        folder = worked_folders[0] if worked_folders else launch_cwd
        worked_inferred = bool(worked_folders and folder != launch_cwd)
        # kiro resume is dir-scoped to the LAUNCH cwd; the cd uses that.
        if launch_cwd:
            cmd = f"cd {_shq(launch_cwd)} && kiro-cli chat --resume-id {sid}"
        else:
            cmd = f"kiro-cli chat --resume-id {sid}"
        yield ResumeTarget(
            cli="kiro-cli",
            session_id=sid,
            folder=folder,
            worked_folders=worked_folders,
            launch_cwd=launch_cwd,
            worked_inferred=worked_inferred,
            title=title,
            updated_at=updated or _iso(ts),
            updated_ts=ts,
            resume_command=cmd,
        )


# --------------------------------------------------------------------------- #
# Claude Code
# --------------------------------------------------------------------------- #
def _claude_meta(jf: Path) -> tuple[str, str, str, float]:
    """Return (cwd, aiTitle, first_user_text, latest_ts) scanning a .jsonl once."""
    cwd = ""
    ai_title = ""
    first_user = ""
    latest_ts = 0.0
    try:
        with jf.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not cwd and d.get("cwd"):
                    cwd = d["cwd"]
                if not ai_title and d.get("type") == "ai-title":
                    ai_title = d.get("aiTitle") or ""
                if not first_user and d.get("type") == "user":
                    msg = d.get("message", {}) or {}
                    content = msg.get("content")
                    if isinstance(content, str):
                        first_user = content
                    elif isinstance(content, list) and content:
                        c0 = content[0]
                        if isinstance(c0, dict):
                            first_user = c0.get("text", "") or ""
                ts = _parse_iso(d.get("timestamp", ""))
                if ts > latest_ts:
                    latest_ts = ts
    except Exception:
        pass
    return cwd, ai_title, first_user, latest_ts


def _decode_project_dir(name: str) -> str:
    """Best-effort decode of Claude's encoded project dir back to a path.

    Claude encodes the cwd by replacing '/' with '-' (leading '-' => '/').
    This is lossy (real dashes vs separators), so it is only a fallback when
    the session's own `cwd` field is absent.
    """
    if not name:
        return ""
    if name.startswith("-"):
        return "/" + name[1:].replace("-", "/")
    return name.replace("-", "/")


def collect_claude(root: Path = CLAUDE_PROJECTS) -> Iterable[ResumeTarget]:
    if not root.is_dir():
        return
    for proj in root.iterdir():
        if not proj.is_dir():
            continue
        for jf in proj.glob("*.jsonl"):
            try:
                sid = jf.stem
                cwd, ai_title, first_user, latest_ts = _claude_meta(jf)
                launch_cwd = cwd or _decode_project_dir(proj.name)
                worked_folders = _infer_cached(jf, launch_cwd, "claude")
                folder = worked_folders[0] if worked_folders else launch_cwd
                worked_inferred = bool(worked_folders and folder != launch_cwd)
                title = _clip(ai_title or first_user or "(untitled)")
                if not latest_ts:
                    try:
                        latest_ts = jf.stat().st_mtime
                    except Exception:
                        latest_ts = 0.0
                # claude --resume must run from the LAUNCH cwd.
                if launch_cwd:
                    cmd = f"cd {_shq(launch_cwd)} && claude --resume {sid}"
                else:
                    cmd = f"claude --resume {sid}"
                yield ResumeTarget(
                    cli="claude",
                    session_id=sid,
                    folder=folder,
                    worked_folders=worked_folders,
                    launch_cwd=launch_cwd,
                    worked_inferred=worked_inferred,
                    title=title,
                    updated_at=_iso(latest_ts),
                    updated_ts=latest_ts,
                    resume_command=cmd,
                )
            except Exception:
                continue


# --------------------------------------------------------------------------- #
# unified
# --------------------------------------------------------------------------- #
def collect_all() -> list[ResumeTarget]:
    out: list[ResumeTarget] = []
    out.extend(collect_kiro())
    out.extend(collect_claude())
    _save_cache()   # persist inference results for fast re-syncs
    # newest first
    out.sort(key=lambda r: r.updated_ts, reverse=True)
    return out


def _session_folders(t: ResumeTarget) -> list[str]:
    """Every folder this session should be grouped under.

    A session is filed under each project it actually worked on. If inference
    found nothing, it falls back to its launch cwd so it still appears somewhere.
    """
    if t.worked_folders:
        return list(dict.fromkeys(t.worked_folders))   # dedupe, keep order
    return [t.launch_cwd or "(unknown folder)"]


# folders that are catch-alls, not real projects — sorted to the bottom
_CATCHALL = {_HOME_STR, "/tmp", "/root", "/", "(unknown folder)"}


def _is_catchall(folder: str) -> bool:
    f = (folder or "").rstrip("/")
    return f in _CATCHALL or f.startswith("/tmp/") or f == ""


def _group_label(folder: str) -> str:
    f = (folder or "").rstrip("/")
    if f == _HOME_STR:
        return "No specific project · home"
    if f == "/tmp" or f.startswith("/tmp/"):
        return "Scratch · " + (os.path.basename(f) or "tmp")
    if f in ("", "(unknown folder)"):
        return "Unknown folder"
    return os.path.basename(f) or f


def group_by_folder(targets: list[ResumeTarget]) -> list[dict]:
    """Group sessions by folder — a multi-project session appears in each of its
    worked-on folders. Real projects are listed first (by recent activity), with
    home/scratch catch-all buckets pushed to the bottom."""
    groups: dict[str, list[ResumeTarget]] = {}
    for t in targets:
        for folder in _session_folders(t):
            groups.setdefault(folder, []).append(t)
    result = []
    for folder, items in groups.items():
        items.sort(key=lambda r: r.updated_ts, reverse=True)
        newest = items[0].updated_ts if items else 0.0
        result.append(
            {
                "folder": folder,
                "name": _group_label(folder),
                "catchall": _is_catchall(folder),
                "count": len(items),
                "kiro": sum(1 for i in items if i.cli == "kiro-cli"),
                "claude": sum(1 for i in items if i.cli == "claude"),
                "latest_ts": newest,
                "latest": _iso(newest),
                "sessions": [i.to_dict() for i in items],
            }
        )
    # real projects first (by recent activity), catch-alls last
    result.sort(key=lambda g: (not g["catchall"], g["latest_ts"]), reverse=True)
    return result


def snapshot() -> dict:
    """The full unified view the bridge persists and the dashboard reads."""
    targets = collect_all()
    groups = group_by_folder(targets)
    now = datetime.now(tz=timezone.utc)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_ts": now.timestamp(),
        "stats": {
            "total": len(targets),
            "kiro": sum(1 for t in targets if t.cli == "kiro-cli"),
            "claude": sum(1 for t in targets if t.cli == "claude"),
            "folders": len(groups),
            "projects": sum(1 for g in groups if not g.get("catchall")),
        },
        "groups": groups,
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
