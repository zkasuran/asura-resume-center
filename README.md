<div align="center">

# 🧭 Asura Resume Center (`arc`)

**Never lose an AI coding session again.**

A local, zero-config dashboard that collects the **resume command for every
[Kiro CLI](https://kiro.dev) and [Claude Code](https://claude.ai/code) session**
— automatically grouped by the project each session actually worked on — with
one-click copy, live sync, and a guarded "free memory" cleanup tool.

![Python](https://img.shields.io/badge/python-3.9%2B-3776ab?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-loopback-009688?logo=fastapi&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Local only](https://img.shields.io/badge/network-127.0.0.1%20only-f85149)

</div>

---

## Why

You run dozens of AI coding sessions across many projects. Days later you want
to pick one back up — but which `--resume` command was it, and in which folder?
Both CLIs bury that in their own session stores, keyed by launch directory, not
by the project you were building.

**ARC** reads both stores, figures out what each session *actually worked on*,
and gives you a single searchable dashboard of ready-to-paste resume commands.

```
kiro-cli ──writes──▶  ~/.kiro/sessions/cli/*.json   ─┐
                                                      ├─▶  arc watcher ──▶  store.json ──▶  dashboard
claude   ──writes──▶  ~/.claude/projects/*/*.jsonl   ─┘
```

It's a passive bridge: it only **reads** your session files, never modifies them.

---

## ✨ Features

- **Both CLIs, one view** — Kiro CLI and Claude Code sessions side by side.
- **Grouped by the real project** — ARC infers the folder(s) a session worked
  on from the files it edited and the commands it ran, not just the launch
  directory. Multi-project sessions appear under *each* project they touched.
- **Click-to-copy resume commands** — `cd '<launch dir>' && kiro-cli chat --resume-id <id>`
  or `… claude --resume <id>`, correct and ready to paste.
- **Live sync** — a background watcher keeps the dashboard current; the page
  auto-refreshes.
- **Search & filter** — by folder, title, command, or CLI.
- **🗑 Free memory** — reclaim disk by deleting old sessions, Claude memory
  files, and whole project directories — with checkboxes, an **age/period
  filter** ("unworked ≥ 30 days"), size totals, and strong safety guards.
- **One command** — just run `arc`.

---

## 🚀 Quick start

```bash
git clone https://github.com/zkasuran/asura-resume-center.git
cd asura-resume-center
./install.sh          # creates the venv, installs deps, symlinks `arc`, starts the services
arc                   # opens the dashboard at http://127.0.0.1:8791/
```

`install.sh` is idempotent and only touches your home dir (`~/.local/bin`,
`~/.config/systemd/user`, `~/.local/share/arc`).

> **Requirements:** Python 3.9+, and [Kiro CLI](https://kiro.dev) and/or
> [Claude Code](https://claude.ai/code) with some existing sessions. Linux with
> `systemd --user` is recommended for the always-on watcher; without it, run
> `arc serve` and `arc watch` manually.

---

## 🖥️ Usage

```text
arc                      open the dashboard (starts the server if needed)

Server / dashboard:
  arc web | serve
  arc start | stop | restart | status | logs

Bridge / sync:
  arc sync                 rebuild the store from disk once
  arc watch                run the watcher in the foreground
  arc watch-start | watch-stop | watch-status

Inspect:
  arc list [filter]        print every resume target (folder · CLI · command)
  arc stats
  arc reap [sessions|memory|projects]   list reclaimable artifacts + sizes
```

---

## 🧠 How "worked-on folder" inference works

For each session, ARC scans the transcript's tool calls (edited/read file
paths, shell commands, working directories), tallies the directories touched,
and folds them to stable project roots (e.g. `~/Downloads/<project>`). It
ignores noise — the CLIs' own stores, `.venv`, `node_modules`, `/tmp` scratch —
and lists every project with a real signal, most-worked first. Results are
cached per transcript (path + mtime) so re-syncs are fast.

The **resume command always uses the session's launch directory** (that's what
`--resume` needs); only the *displayed* grouping reflects the worked-on project.

---

## 🗑️ Free memory — safe by design

Deletion is permanent, so it is guarded:

- **Loopback-only, no remote access.** The server binds `127.0.0.1`.
- **Explicit selection + two-step confirm** (type `DELETE`).
- **Path validation.** Session/memory/project deletes are restricted to
  `~/.kiro/sessions/cli` and `~/.claude/projects`.
- **Working-folder deletion is extra-guarded.** The optional "also delete
  working folders" mode refuses `$HOME`, workspace bases (`~/Downloads`, …),
  system roots, the CLI stores, and ARC itself — only genuine project
  directories are eligible, and they are listed before you confirm.

---

## 🔒 Privacy

ARC is **100% local**. It reads your session files, builds an index on disk at
`~/.local/share/arc/`, and serves it only on `127.0.0.1`. Nothing is uploaded
anywhere. No telemetry, no accounts, no network egress.

---

## 🧩 Project layout

```
asura-resume-center/
├── arc-run                 # bash launcher (symlinked to ~/.local/bin/arc)
├── arc.py                  # CLI driver
├── install.sh              # one-shot installer
├── requirements.txt
├── systemd/                # user-service templates (install.sh fills the path)
│   ├── arc.service.in
│   └── arc-watch.service.in
└── arc/
    ├── collector.py        # parse both CLIs → resume targets + worked-folder inference
    ├── store.py            # atomic JSON sync store
    ├── reaper.py           # enumerate + guarded delete (sessions/memory/projects/folders)
    ├── server.py           # FastAPI loopback API + dashboard
    ├── dashboard_ui.py     # the dark 9router-style dashboard
    └── watcher.py          # background sync watcher
```

---

## ⚙️ Configuration

| Env var              | Default      | Meaning                         |
|----------------------|--------------|---------------------------------|
| `ARC_HOST`           | `127.0.0.1`  | server bind host                |
| `ARC_PORT`           | `8791`       | server port                     |
| `ARC_WATCH_INTERVAL` | `15`         | watcher sync interval (seconds) |

---

## 📄 License

[MIT](./LICENSE) © zkasuran
