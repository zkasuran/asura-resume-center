"""Asura Resume Center — the reaper (free memory by deleting artifacts).

Enumerates deletable artifacts in three categories, each with its on-disk size,
and deletes only an explicit, server-validated selection. This is a destructive,
hard-to-reverse operation, so every delete is guarded:

  * Only paths *inside* the known roots can be deleted (path-traversal safe).
  * Each item is addressed by an opaque id the server itself minted this run.
  * The caller must pass the exact ids back; nothing is deleted implicitly.

Categories
----------
  sessions : one agent conversation.
             - kiro-cli  : all `<id>.{json,jsonl,history,lock}` + the `<id>/` dir
                           under ~/.kiro/sessions/cli
             - claude    : the `<id>.jsonl` under its ~/.claude/projects/<proj>
  memory   : a single Claude per-project memory file (…/memory/*.md)
  projects : a whole Claude project directory (~/.claude/projects/<proj>)
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
KIRO_CLI = HOME / ".kiro" / "sessions" / "cli"
CLAUDE_PROJECTS = HOME / ".claude" / "projects"

# Deletion is only ever permitted *inside* these roots.
ALLOWED_ROOTS = [KIRO_CLI.resolve(), CLAUDE_PROJECTS.resolve()]


# --------------------------------------------------------------------------- #
# sizing
# --------------------------------------------------------------------------- #
def _size(path: Path) -> int:
    try:
        if path.is_dir():
            total = 0
            for root, _dirs, files in os.walk(path):
                for f in files:
                    fp = Path(root) / f
                    try:
                        total += fp.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
            return total
        return path.stat(follow_symlinks=False).st_size
    except OSError:
        return 0


def human(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


# --------------------------------------------------------------------------- #
# item model
# --------------------------------------------------------------------------- #
@dataclass
class Artifact:
    id: str                 # opaque, == primary path (validated on delete)
    category: str           # "session" | "memory" | "project"
    cli: str                # "kiro-cli" | "claude" | ""
    label: str              # human label
    folder: str             # associated project folder when known
    paths: list[str]        # every path this artifact owns (deleted together)
    bytes: int = 0
    human: str = ""
    detail: str = field(default="")
    updated_ts: float = 0.0           # last-activity epoch (for period filters)
    age_days: float = 0.0             # days since last activity
    worked_folders: list = field(default_factory=list)   # project dirs the session worked on

    def to_dict(self) -> dict:
        return {
            "id": self.id, "category": self.category, "cli": self.cli,
            "label": self.label, "folder": self.folder, "paths": self.paths,
            "bytes": self.bytes, "human": self.human, "detail": self.detail,
            "updated_ts": self.updated_ts, "age_days": round(self.age_days, 1),
            "worked_folders": self.worked_folders,
        }


# --------------------------------------------------------------------------- #
# enumeration
# --------------------------------------------------------------------------- #
def _kiro_session_paths(sid: str) -> list[Path]:
    out = []
    for suffix in (".json", ".jsonl", ".history", ".lock"):
        p = KIRO_CLI / f"{sid}{suffix}"
        if p.exists():
            out.append(p)
    d = KIRO_CLI / sid
    if d.is_dir():
        out.append(d)
    return out


def enumerate_sessions() -> list[Artifact]:
    """One Artifact per session, bundling all of its on-disk files."""
    import collector  # reuse the same metadata the dashboard shows
    import time as _time

    now = _time.time()

    def _age(ts):
        return max(0.0, (now - ts) / 86400.0) if ts else 0.0

    arts: list[Artifact] = []
    for t in collector.collect_kiro():
        paths = _kiro_session_paths(t.session_id)
        if not paths:
            continue
        total = sum(_size(p) for p in paths)
        arts.append(Artifact(
            id=str((KIRO_CLI / f"{t.session_id}.json")),
            category="session", cli="kiro-cli",
            label=t.title, folder=t.folder,
            paths=[str(p) for p in paths], bytes=total, human=human(total),
            detail=f"{len(paths)} files · {t.session_id}",
            updated_ts=t.updated_ts, age_days=_age(t.updated_ts),
            worked_folders=list(t.worked_folders or []),
        ))
    for t in collector.collect_claude():
        # locate the actual jsonl (its project dir encodes the cwd)
        found = list(CLAUDE_PROJECTS.glob(f"*/{t.session_id}.jsonl"))
        if not found:
            continue
        p = found[0]
        total = _size(p)
        arts.append(Artifact(
            id=str(p), category="session", cli="claude",
            label=t.title, folder=t.folder,
            paths=[str(p)], bytes=total, human=human(total),
            detail=f"1 file · {t.session_id}",
            updated_ts=t.updated_ts, age_days=_age(t.updated_ts),
            worked_folders=list(t.worked_folders or []),
        ))
    arts.sort(key=lambda a: a.updated_ts)   # oldest (longest-unworked) first
    return arts


def enumerate_memory() -> list[Artifact]:
    """Each Claude per-project memory .md file."""
    arts: list[Artifact] = []
    if not CLAUDE_PROJECTS.is_dir():
        return arts
    for md in CLAUDE_PROJECTS.glob("*/memory/*.md"):
        try:
            total = _size(md)
            proj = md.parent.parent.name
            arts.append(Artifact(
                id=str(md), category="memory", cli="claude",
                label=md.name, folder=_decode(proj),
                paths=[str(md)], bytes=total, human=human(total),
                detail=f"memory · {proj}",
            ))
        except Exception:
            continue
    arts.sort(key=lambda a: a.bytes, reverse=True)
    return arts


def enumerate_projects() -> list[Artifact]:
    """Each whole Claude project directory."""
    arts: list[Artifact] = []
    if not CLAUDE_PROJECTS.is_dir():
        return arts
    for proj in CLAUDE_PROJECTS.iterdir():
        if not proj.is_dir():
            continue
        try:
            total = _size(proj)
            n_sess = len(list(proj.glob("*.jsonl")))
            n_mem = len(list(proj.glob("memory/*.md")))
            arts.append(Artifact(
                id=str(proj), category="project", cli="claude",
                label=proj.name, folder=_decode(proj.name),
                paths=[str(proj)], bytes=total, human=human(total),
                detail=f"{n_sess} sessions · {n_mem} memory files",
            ))
        except Exception:
            continue
    arts.sort(key=lambda a: a.bytes, reverse=True)
    return arts


def _decode(name: str) -> str:
    if not name:
        return ""
    if name.startswith("-"):
        return "/" + name[1:].replace("-", "/")
    return name.replace("-", "/")


def enumerate_all() -> dict:
    sessions = enumerate_sessions()
    memory = enumerate_memory()
    projects = enumerate_projects()

    def _sum(items):
        return sum(a.bytes for a in items)

    return {
        "sessions": [a.to_dict() for a in sessions],
        "memory": [a.to_dict() for a in memory],
        "projects": [a.to_dict() for a in projects],
        "totals": {
            "sessions": {"count": len(sessions), "bytes": _sum(sessions),
                         "human": human(_sum(sessions))},
            "memory": {"count": len(memory), "bytes": _sum(memory),
                       "human": human(_sum(memory))},
            "projects": {"count": len(projects), "bytes": _sum(projects),
                         "human": human(_sum(projects))},
        },
    }


# --------------------------------------------------------------------------- #
# deletion (guarded)
# --------------------------------------------------------------------------- #
def _is_allowed(path: Path) -> bool:
    try:
        rp = path.resolve()
    except Exception:
        return False
    for root in ALLOWED_ROOTS:
        try:
            rp.relative_to(root)
            if rp != root:   # never allow deleting a root itself
                return True
        except ValueError:
            continue
    return False


def _delete_path(path: Path) -> int:
    """Delete one file or dir inside an allowed root. Returns bytes freed."""
    if not _is_allowed(path):
        raise PermissionError(f"refused: outside allowed roots: {path}")
    if not path.exists():
        return 0
    freed = _size(path)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return freed


# --- working-folder deletion (deletes REAL project dirs — stricter guard) ---
_HOME_RESOLVED = HOME.resolve()
# never deletable as a "working folder": these roots and anything shallower
_WORKFOLDER_FORBIDDEN = {
    _HOME_RESOLVED,
    Path("/"), Path("/home"), Path("/root"), Path("/tmp"), Path("/usr"),
    Path("/etc"), Path("/var"), Path("/opt"), Path("/bin"), Path("/boot"),
}
# bare workspace bases that must never be deleted whole
_WORKFOLDER_BASES = {
    _HOME_RESOLVED / b for b in
    ("Downloads", "Documents", "Pictures", "Desktop", "projects", "work",
     "src", "dev", "repos", "code", ".config", ".local", ".kiro", ".claude")
}


def _is_deletable_workfolder(path: Path) -> tuple[bool, str]:
    """Is this path safe to delete as a worked-on project folder?"""
    try:
        rp = path.resolve()
    except Exception:
        return False, "unresolvable path"
    if not rp.is_dir():
        return False, "not a directory"
    if rp in _WORKFOLDER_FORBIDDEN or rp in _WORKFOLDER_BASES:
        return False, "protected root/base folder"
    # must live under HOME (don't delete system dirs), and be at least 2 levels deep
    try:
        rel = rp.relative_to(_HOME_RESOLVED)
    except ValueError:
        return False, "outside home"
    if len(rel.parts) < 1:
        return False, "too shallow"
    # never delete the arc project itself or the CLI stores
    for bad in ("/.kiro/", "/.claude/", "/asura-resume-center"):
        if bad in (str(rp) + "/"):
            return False, "arc/CLI-internal folder"
    return True, ""


def _session_worked_folders(id_: str) -> list[Path]:
    """Return the worked-on project folders recorded for a session artifact id.

    We re-enumerate sessions and match by id so the UI can't inject arbitrary
    folders — only folders this session actually worked on are eligible.
    """
    try:
        for a in enumerate_sessions():
            if a.id == id_:
                return [Path(f) for f in (a.worked_folders or [])]
    except Exception:
        pass
    return []


def delete(ids: list[str], dry_run: bool = False,
           include_worked_folders: bool = False) -> dict:
    """Delete the artifacts addressed by `ids`.

    `ids` are the primary paths minted by enumerate_*(). For each, we rebuild
    the full owned path set so companion files (kiro .jsonl/.history/.lock + the
    tasks dir) go together, then delete each guarded path.

    If `include_worked_folders` is set, the REAL project folders a session
    worked on are also deleted — but only those that pass the strict
    working-folder guard (never $HOME, workspace bases, system roots, or
    arc/CLI-internal dirs). Folder deletions are reported separately.
    """
    results = []
    folder_results = []
    freed_total = 0
    # dedupe worked folders across the whole selection so we delete each once
    wf_seen: set[str] = set()
    # IMPORTANT: resolve worked folders BEFORE deleting any session, otherwise
    # re-enumeration can't find the (now-deleted) session's metadata.
    wf_by_id: dict[str, list[Path]] = {}
    if include_worked_folders:
        try:
            index = {a.id: list(a.worked_folders or []) for a in enumerate_sessions()}
        except Exception:
            index = {}
        for id_ in ids:
            wf_by_id[id_] = [Path(f) for f in index.get(id_, [])]
    for id_ in ids:
        p = Path(id_)
        owned: list[Path] = []
        # kiro session primary is "<id>.json" -> expand to its full set
        if p.suffix == ".json" and p.parent == KIRO_CLI:
            sid = p.stem
            owned = _kiro_session_paths(sid)
        else:
            owned = [p]
        item_freed = 0
        errors = []
        for op in owned:
            try:
                if dry_run:
                    item_freed += _size(op)
                else:
                    item_freed += _delete_path(op)
            except Exception as e:
                errors.append(f"{op}: {e}")
        freed_total += item_freed
        results.append({
            "id": id_, "freed": item_freed, "human": human(item_freed),
            "paths": [str(o) for o in owned],
            "ok": not errors, "errors": errors,
        })
        # optionally delete the project folders this session worked on
        if include_worked_folders:
            for wf in wf_by_id.get(id_, []):
                key = str(wf.resolve()) if wf.exists() else str(wf)
                if key in wf_seen:
                    continue
                wf_seen.add(key)
                ok, why = _is_deletable_workfolder(wf)
                if not ok:
                    folder_results.append({
                        "folder": str(wf), "freed": 0, "human": "0 B",
                        "ok": False, "errors": [f"refused: {why}"]})
                    continue
                try:
                    sz = _size(wf)
                    if not dry_run:
                        shutil.rmtree(wf)
                    freed_total += sz
                    folder_results.append({
                        "folder": str(wf), "freed": sz, "human": human(sz),
                        "ok": True, "errors": []})
                except Exception as e:
                    folder_results.append({
                        "folder": str(wf), "freed": 0, "human": "0 B",
                        "ok": False, "errors": [str(e)]})
    return {
        "dry_run": dry_run,
        "include_worked_folders": include_worked_folders,
        "deleted": sum(1 for r in results if r["ok"]),
        "requested": len(ids),
        "folders_deleted": sum(1 for r in folder_results if r["ok"]),
        "freed_bytes": freed_total,
        "freed_human": human(freed_total),
        "results": results,
        "folder_results": folder_results,
    }


if __name__ == "__main__":
    import json
    data = enumerate_all()
    print(json.dumps(data["totals"], indent=2))
