#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CFG_PATH = os.path.expanduser("~/printer_data/config/drukmix_driver.cfg")


@dataclasses.dataclass
class Cfg:
    backend: str
    transport: str
    serial_port: str
    serial_baud: int
    fake_bridge_log: str
    fake_max_lpm: float
    fake_tau_up_s: float
    fake_tau_down_s: float
    fake_running_threshold_pct: float
    status_file: str


def _strip_inline_comment(v: str) -> str:
    if v is None:
        return ""
    v = str(v)
    v = v.split("#", 1)[0]
    v = v.split(";", 1)[0]
    return v.strip()


def _get_str(s: configparser.SectionProxy, key: str, default: str) -> str:
    return _strip_inline_comment(s.get(key, default))


def _get_int(s: configparser.SectionProxy, key: str, default: int) -> int:
    raw = s.get(key, str(default))
    return int(float(_strip_inline_comment(raw)))


def _get_float(s: configparser.SectionProxy, key: str, default: float) -> float:
    raw = s.get(key, str(default))
    return float(_strip_inline_comment(raw))


def load_cfg(path: str) -> Cfg:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cp.read(path):
        raise FileNotFoundError(path)
    s = cp["drukmix_driver"]
    return Cfg(
        backend=_get_str(s, "backend", "pumpvfd"),
        transport=_get_str(s, "transport", "usb").lower(),
        serial_port=_get_str(s, "serial_port", "/dev/drukos-bridge"),
        serial_baud=_get_int(s, "serial_baud", 921600),
        fake_bridge_log=_get_str(
            s, "fake_bridge_log", "/tmp/drukmix_fake_bridge.jsonl"
        ),
        fake_max_lpm=_get_float(s, "fake_max_lpm", 10.0),
        fake_tau_up_s=_get_float(s, "fake_tau_up_s", 1.0),
        fake_tau_down_s=_get_float(s, "fake_tau_down_s", 0.8),
        fake_running_threshold_pct=_get_float(s, "fake_running_threshold_pct", 2.0),
        status_file=_get_str(
            s,
            "status_file",
            os.path.expanduser("~/printer_data/logs/drukmix_status.json"),
        ),
    )


def load_snapshot(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def backend_from_cfg(cfg):
    from backend.backend_pumptpl import PumpTplBackend
    from backend.backend_pumpvfd import PumpVfdBackend
    from backend.bridge_fake_transport import FakeBridgeTransport
    from backend.bridge_usb_transport import BridgeUsbTransport

    if cfg.transport == "fake":
        transport = FakeBridgeTransport(
            log_jsonl=cfg.fake_bridge_log,
            max_lpm=cfg.fake_max_lpm,
            tau_up_s=cfg.fake_tau_up_s,
            tau_down_s=cfg.fake_tau_down_s,
            running_threshold_pct=cfg.fake_running_threshold_pct,
        )
    else:
        transport = BridgeUsbTransport(cfg.serial_port, cfg.serial_baud)

    if cfg.backend == "pumptpl":
        backend = PumpTplBackend(transport)
    else:
        backend = PumpVfdBackend(transport)
    return transport, backend


def direct_status(cfg):
    transport, backend = backend_from_cfg(cfg)
    backend.open()
    try:
        status = backend.poll_status()
    finally:
        backend.close()
    return {
        "updated_unix_s": time.time(),
        "source": "direct",
        "backend": dataclasses.asdict(status),
    }


def print_human(payload: dict):
    backend = payload.get("backend") or {}
    updated_unix_s = payload.get("updated_unix_s")
    source = payload.get("source", "snapshot")
    age_s = None
    if isinstance(updated_unix_s, (int, float)):
        age_s = max(0.0, time.time() - float(updated_unix_s))

    faulted = bool(backend.get("faulted", False))
    fault_code = int(backend.get("fault_code", -1))
    running = backend.get("running")
    if running is None:
        running_text = "unknown"
    else:
        running_text = "yes" if bool(running) else "no"

    lines = [
        f"Source: {source}",
        f"Age: {age_s:.1f}s" if age_s is not None else "Age: unknown",
        f"Backend: {backend.get('backend', 'unknown')}",
        f"Mode: {backend.get('control_mode', 'UNKNOWN')}",
        f"Link: {'OK' if backend.get('link_ok') else 'FAIL'}",
        f"Running: {running_text}",
        f"Fault: {'yes' if faulted else 'no'}",
    ]
    if faulted:
        lines.append(
            f"Fault Detail: code={fault_code} text={backend.get('fault_text') or backend.get('fault_name') or ''}".rstrip()
        )
    lines.extend(
        [
            f"Target %: {backend.get('target_pct')}",
            f"Age ms: {backend.get('age_ms')}",
            f"Pump Mode: {backend.get('pump_mode')}",
            f"Pump Flags: {backend.get('pump_flags')}",
            f"HW Setpoint Raw: {backend.get('hw_setpoint_raw')}",
            f"Last Ack Seq: {backend.get('last_ack_seq')}",
            f"Applied Code: {backend.get('applied_code')}",
        ]
    )
    print("\n".join(lines))


def cmd_check(args):
    cfg = load_cfg(args.config)
    snapshot_path = Path(cfg.status_file)

    payload = None
    if not args.direct:
        payload = load_snapshot(snapshot_path)
        if payload is not None:
            payload = dict(payload)
            payload.setdefault("source", "snapshot")

    if payload is None:
        payload = direct_status(cfg)

    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print_human(payload)
    return 0


def cmd_unavailable(args):
    print(
        "Production VFD register service plane is not implemented yet in the bridge/pump_vfd path.\n"
        "Use 'pump_vfd_debug' for raw register work, or add the VFD service plane next.",
        file=sys.stderr,
    )
    return 2


def build_parser():
    ap = argparse.ArgumentParser(prog="vfd_cli.py")
    ap.add_argument("--config", default=str(DEFAULT_CFG_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_check = sub.add_parser("check")
    ap_check.add_argument("--json", action="store_true")
    ap_check.add_argument("--direct", action="store_true")
    ap_check.set_defaults(func=cmd_check)

    ap_read = sub.add_parser("read")
    ap_read.add_argument("reg")
    ap_read.set_defaults(func=cmd_unavailable)

    ap_write = sub.add_parser("write")
    ap_write.add_argument("reg")
    ap_write.add_argument("value")
    ap_write.set_defaults(func=cmd_unavailable)

    ap_preset = sub.add_parser("preset")
    ap_preset.add_argument("action", nargs="?", default="list")
    ap_preset.add_argument("name", nargs="?")
    ap_preset.set_defaults(func=cmd_unavailable)
    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()
    try:
        raise SystemExit(args.func(args))
    except FileNotFoundError as exc:
        print(f"Required file not found: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except ModuleNotFoundError as exc:
        print(
            f"Missing Python module for VFD direct access: {exc.name}. "
            "Run 'drukmix install <profile>' first or use the repo venv.",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
