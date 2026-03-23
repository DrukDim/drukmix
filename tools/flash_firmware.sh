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

for f in bootloader.bin partitions.bin boot_app0.bin firmware.bin; do
  [[ -f "$DIR/$f" ]] || { echo "missing $DIR/$f"; exit 2; }
done

python3 -m esptool --chip esp32 --port "$PORT" --baud "$BAUD" write_flash -z \
  0x1000 "$DIR/bootloader.bin" \
  0x8000 "$DIR/partitions.bin" \
  0xe000 "$DIR/boot_app0.bin" \
  0x10000 "$DIR/firmware.bin"
