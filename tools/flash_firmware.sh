#!/usr/bin/env bash
set -euo pipefail

APP="${1:-}"
PORT="${2:-}"
BAUD="${3:-921600}"

if [[ -z "$APP" || -z "$PORT" ]]; then
  echo "usage: tools/flash_firmware.sh <bridge|pump_vfd|pump_tpl> <port> [baud]"
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/firmware/releases/$APP"
VENV_PY="$ROOT/.venv/bin/python"

for f in bootloader.bin partitions.bin boot_app0.bin firmware.bin; do
  [[ -f "$DIR/$f" ]] || { echo "missing $DIR/$f"; exit 2; }
done

python_has_module() {
  local py="$1"
  "$py" - <<'PY' >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("esptool") else 1)
PY
}

resolve_esptool_python() {
  if python_has_module python3; then
    printf '%s\n' python3
    return 0
  fi

  if [[ -x "$VENV_PY" ]]; then
    if ! python_has_module "$VENV_PY"; then
      echo "Installing esptool into repo venv: $VENV_PY" >&2
      "$VENV_PY" -m pip install esptool >&2
    fi
    if python_has_module "$VENV_PY"; then
      printf '%s\n' "$VENV_PY"
      return 0
    fi
  fi

  echo "No Python interpreter with esptool available." >&2
  echo "Run 'drukmix install <profile>' first, or install esptool for python3." >&2
  return 1
}

ESPTOOL_PY="$(resolve_esptool_python)"
declare -a baud_candidates=()
baud_candidates+=("$BAUD")
for fallback in 460800 230400 115200; do
  if [[ "$fallback" != "$BAUD" ]]; then
    baud_candidates+=("$fallback")
  fi
done

last_rc=0
for try_baud in "${baud_candidates[@]}"; do
  echo "Flashing $APP on $PORT at $try_baud baud"
  if "$ESPTOOL_PY" -m esptool --chip esp32 --port "$PORT" --baud "$try_baud" write_flash -z \
    0x1000 "$DIR/bootloader.bin" \
    0x8000 "$DIR/partitions.bin" \
    0xe000 "$DIR/boot_app0.bin" \
    0x10000 "$DIR/firmware.bin"; then
    exit 0
  fi
  last_rc=$?
  echo "Flash failed at $try_baud baud, trying lower speed..." >&2
done

exit "$last_rc"
