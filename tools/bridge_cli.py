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
    serial_port: str
    serial_baud: int


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


def load_cfg(path: str) -> Cfg:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cp.read(path):
        raise FileNotFoundError(path)
    s = cp["drukmix_driver"]
    return Cfg(
        serial_port=_get_str(s, "serial_port", "/dev/drukos-bridge"),
        serial_baud=_get_int(s, "serial_baud", 921600),
    )


def _resolve_port(path: str) -> dict[str, str | bool]:
    p = Path(path)
    info: dict[str, str | bool] = {
        "port": str(p),
        "port_exists": p.exists(),
        "port_is_symlink": p.is_symlink(),
        "port_target": "",
    }
    if p.exists():
        try:
            info["port_target"] = str(p.resolve())
        except OSError:
            info["port_target"] = ""
    return info


def probe_status(cfg: Cfg, attempts: int) -> dict:
    from backend.bridge_usb_transport import BridgeUsbTransport

    transport = BridgeUsbTransport(cfg.serial_port, cfg.serial_baud)
    raw = None
    started_unix_s = time.time()
    transport.open()
    try:
        for _ in range(max(1, attempts)):
            raw = transport.read_status(allow_cached=False)
            if raw is not None:
                break
    finally:
        transport.close()

    payload = {
        "updated_unix_s": started_unix_s,
        "source": "direct",
        "transport": "bridge-usb",
        "bridge_ok": raw is not None,
        "bridge_status": raw,
    }
    payload.update(_resolve_port(cfg.serial_port))
    payload["serial_baud"] = cfg.serial_baud
    return payload


def print_human(payload: dict):
    st = payload.get("bridge_status") or {}

    lines = [
        "Source: direct",
        f"Transport: {payload.get('transport', 'unknown')}",
        f"Port: {payload.get('port', 'unknown')}",
        f"Port Exists: {'yes' if payload.get('port_exists') else 'no'}",
        f"Port Symlink: {'yes' if payload.get('port_is_symlink') else 'no'}",
        f"Port Target: {payload.get('port_target') or '-'}",
        f"Baud: {payload.get('serial_baud')}",
        f"Bridge USB Status: {'OK' if payload.get('bridge_ok') else 'FAIL'}",
    ]

    if not payload.get("bridge_ok"):
        lines.extend(
            [
                "Reason: no valid USB bridge status packet received",
                "Hints: check bridge power, USB alias/port, bridge firmware, or wrong CP2102 attached",
            ]
        )
        print("\n".join(lines))
        return

    lines.extend(
        [
            f"Pump Link: {'OK' if st.get('link_ok') else 'FAIL'}",
            f"Control Mode: {st.get('control_mode', 'UNKNOWN')}",
            f"Pump Mode Raw: {st.get('pump_mode')}",
            f"Pump Flags: {st.get('pump_flags')}",
            f"Pump Online: {'yes' if st.get('pump_online') else 'no'}",
            f"Pump Running: {'yes' if st.get('running') else 'no'}",
            f"Pump State Raw: {st.get('pump_state')}",
            f"Fault Code: {st.get('fault_code')}",
            f"Age ms: {st.get('age_ms')}",
            f"Target mL/min x1000: {st.get('target_milli_lpm')}",
            f"HW Setpoint Raw: {st.get('hw_setpoint_raw')}",
            f"Last Ack Seq: {st.get('last_ack_seq')}",
            f"Applied Code: {st.get('applied_code')}",
            f"Error Flags: {st.get('err_flags')}",
            f"Retry Count: {st.get('retry_count')}",
            f"Send Fail Count: {st.get('send_fail_count')}",
            f"Bridge Seq Reply: {st.get('seq_reply')}",
        ]
    )
    print("\n".join(lines))


def cmd_check(args):
    cfg = load_cfg(args.config)
    payload = probe_status(cfg, attempts=args.attempts)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print_human(payload)
    return 0 if payload.get("bridge_ok") else 1


def build_parser():
    ap = argparse.ArgumentParser(prog="bridge_cli.py")
    ap.add_argument("--config", default=str(DEFAULT_CFG_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_check = sub.add_parser("check")
    ap_check.add_argument("--json", action="store_true")
    ap_check.add_argument("--attempts", type=int, default=3)
    ap_check.set_defaults(func=cmd_check)
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
            f"Missing Python module for bridge access: {exc.name}. "
            "Run 'drukmix install <profile>' first or use the repo venv.",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
