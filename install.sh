#!/usr/bin/env bash
# Asura Resume Center — installer.
# Idempotent. Only touches your home dir. No root, no network beyond pip.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

echo "Asura Resume Center → installing from $APP_DIR"

# 1) virtualenv + deps
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  echo "  • creating venv"
  python3 -m venv "$APP_DIR/.venv"
fi
echo "  • installing dependencies"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# 2) global `arc` command
mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/arc-run" "$BIN_DIR/arc"
chmod +x "$APP_DIR/arc-run" "$APP_DIR/arc.py"
echo "  • linked $BIN_DIR/arc"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "    ⚠ add $BIN_DIR to your PATH to use 'arc' directly";;
esac

# 3) systemd user services (optional — only if systemd --user is available)
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$UNIT_DIR"
  for svc in arc arc-watch; do
    sed "s#@APP_DIR@#$APP_DIR#g" "$APP_DIR/systemd/$svc.service.in" > "$UNIT_DIR/$svc.service"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now arc.service arc-watch.service
  echo "  • systemd services enabled (arc.service, arc-watch.service)"
else
  echo "  • systemd --user not available — run 'arc serve' and 'arc watch' manually"
fi

echo
echo "✓ Installed. Run:  arc        (opens http://127.0.0.1:8791/)"
