#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export_one() {
  local app="$1"
  local build_dir="$ROOT/firmware/$app/.pio/build/$app"
  local out_dir="$ROOT/firmware/releases/$app"

  mkdir -p "$out_dir"

  cp -f "$build_dir/firmware.bin" "$out_dir/"
  cp -f "$build_dir/firmware.elf" "$out_dir/"
  cp -f "$build_dir/bootloader.bin" "$out_dir/"
  cp -f "$build_dir/partitions.bin" "$out_dir/"

  if [ -f "$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin" ]; then
    cp -f "$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin" "$out_dir/"
  elif [ -f "$HOME/.platformio/packages/framework-arduinoespressif32@3.20017.241212/tools/partitions/boot_app0.bin" ]; then
    cp -f "$HOME/.platformio/packages/framework-arduinoespressif32@3.20017.241212/tools/partitions/boot_app0.bin" "$out_dir/"
  else
    echo "boot_app0.bin not found in PlatformIO packages"
    exit 2
  fi

  cat > "$out_dir/flash_args.txt" <<ARGS
0x1000 bootloader.bin
0x8000 partitions.bin
0xe000 boot_app0.bin
0x10000 firmware.bin
ARGS
}

export_one bridge
export_one pump_tpl
export_one pump_vfd

echo "Exported firmware artifacts to:"
echo "  firmware/releases/bridge"
echo "  firmware/releases/pump_tpl"
echo "  firmware/releases/pump_vfd"
