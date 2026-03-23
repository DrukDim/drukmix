#!/usr/bin/env bash
#
# Start DrukMix fake bridge (PTY) and create a stable symlink.
#
# Usage:
#   ./fake_bridge_start.sh
#   ./fake_bridge_start.sh /tmp/drukmix_fake_bridge
#
# Environment overrides:
#   BRIDGE_LOG      (default: /tmp/drukmix_fake_bridge.jsonl)
#   BRIDGE_TTY_FILE (default: /tmp/drukmix_fake_bridge_tty)
#   BRIDGE_SYMLINK  (default: /tmp/drukmix_fake_bridge)
#   PYTHON_BIN      (default: /home/drukos/drukmix/.venv/bin/python)
#   BRIDGE_SCRIPT   (default: /home/drukos/drukmix/tools/lab/fake_bridge_pty.py)
#
set -euo pipefail

BRIDGE_LOG="${BRIDGE_LOG:-/tmp/drukmix_fake_bridge.jsonl}"
BRIDGE_TTY_FILE="${BRIDGE_TTY_FILE:-/tmp/drukmix_fake_bridge_tty}"
BRIDGE_SYMLINK="${BRIDGE_SYMLINK:-/tmp/drukmix_fake_bridge}"
PYTHON_BIN="${PYTHON_BIN:-/home/drukos/drukmix/.venv/bin/python}"
BRIDGE_SCRIPT="${BRIDGE_SCRIPT:-/home/drukos/drukmix/tools/lab/fake_bridge_pty.py}"

if [[ $# -ge 1 ]]; then
  BRIDGE_SYMLINK="$1"
fi

log() { printf "[fake-bridge] %s\n" "$*" >&2; }

if [[ ! -x "$PYTHON_BIN" ]]; then
  log "Python not found/executable: $PYTHON_BIN"
  exit 1
fi

if [[ ! -f "$BRIDGE_SCRIPT" ]]; then
  log "Bridge script not found: $BRIDGE_SCRIPT"
  exit 1
fi

# Start fake bridge (non-blocking)
nohup "$PYTHON_BIN" "$BRIDGE_SCRIPT" \
  --log-jsonl "$BRIDGE_LOG" \
  --write-tty-path "$BRIDGE_TTY_FILE" \
  >/tmp/drukmix_fake_bridge.out 2>&1 &

sleep 0.2

if [[ ! -s "$BRIDGE_TTY_FILE" ]]; then
  log "No PTY path written to $BRIDGE_TTY_FILE"
  exit 1
fi

TTY_PATH="$(cat "$BRIDGE_TTY_FILE")"
ln -sf "$TTY_PATH" "$BRIDGE_SYMLINK"

log "started: $BRIDGE_SCRIPT"
log "pty: $TTY_PATH"
log "symlink: $BRIDGE_SYMLINK -> $TTY_PATH"
log "log: $BRIDGE_LOG"
