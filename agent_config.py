from __future__ import annotations
import configparser
import dataclasses
import math
import os
import re


@dataclasses.dataclass
class Cfg:
    enabled: bool
    moonraker_ws: str
    serial_port: str
    serial_baud: int

    client_name: str
    client_version: str
    client_type: str
    client_url: str

    pump_max_lpm: float
    min_run_lpm: float
    min_run_hold_s: float
    flow_gain: float

    retract_deadband_mm_s: float
    retract_gain: float

    printer_cfg: str
    filament_diameter_fallback: float

    update_hz: float
    poll_hz: float

    pause_on_pump_offline: bool
    pause_on_manual_during_print: bool
    ui_notify: bool

    bridge_offline_timeout_s: float
    pump_offline_timeout_s: float

    log_file: str
    log_level: str
    log_period_s: float

    flush_burst_count: int
    flush_burst_interval_ms: int
    flush_confirm: bool
    flush_confirm_timeout_s: float
    flush_confirm_tolerance_code: int
    flush_confirm_retries: int

    cfg_reload_s: float
    cfg_path: str = ""


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _strip_inline_comment(v: str) -> str:
    if v is None:
        return ""
    v = str(v)
    v = v.split("#", 1)[0]
    v = v.split(";", 1)[0]
    return v.strip()


def _get_float(s: configparser.SectionProxy, key: str, default: float) -> float:
    raw = s.get(key, str(default))
    return float(_strip_inline_comment(raw))


def _get_int(s: configparser.SectionProxy, key: str, default: int) -> int:
    raw = s.get(key, str(default))
    return int(float(_strip_inline_comment(raw)))


def _get_str(s: configparser.SectionProxy, key: str, default: str) -> str:
    raw = s.get(key, default)
    return _strip_inline_comment(raw)


def load_config(path: str) -> Cfg:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cp.read(path):
        raise FileNotFoundError(path)
    s = cp["drukmix"]

    def get_bool(k, d=False):
        raw = s.get(k, str(d))
        raw = _strip_inline_comment(raw).lower()
        return raw in ("1", "true", "yes", "on")

    return Cfg(
        enabled=get_bool("enabled", True),
        moonraker_ws=_get_str(s, "moonraker_ws", "ws://127.0.0.1:7125/websocket"),
        serial_port=_get_str(s, "serial_port", ""),
        serial_baud=_get_int(s, "serial_baud", 921600),

        client_name=_get_str(s, "client_name", "drukmix"),
        client_version=_get_str(s, "client_version", "2.2.0"),
        client_type=_get_str(s, "client_type", "agent"),
        client_url=_get_str(s, "client_url", "https://drukos.local/drukmix"),

        pump_max_lpm=_get_float(s, "pump_max_lpm", 10.0),
        min_run_lpm=_get_float(s, "min_run_lpm", 0.20),
        min_run_hold_s=_get_float(s, "min_run_hold_s", 5.0),
        flow_gain=_get_float(s, "flow_gain", 1.0),

        retract_deadband_mm_s=_get_float(s, "retract_deadband_mm_s", 0.20),
        retract_gain=_get_float(s, "retract_gain", 1.0),

        printer_cfg=_get_str(s, "printer_cfg", os.path.expanduser("~/printer_data/config/printer.cfg")),
        filament_diameter_fallback=_get_float(s, "filament_diameter_fallback", 35.0),

        update_hz=_get_float(s, "update_hz", 6.0),
        poll_hz=_get_float(s, "poll_hz", 0.5),

        pause_on_pump_offline=get_bool("pause_on_pump_offline", True),
        pause_on_manual_during_print=get_bool("pause_on_manual_during_print", True),
        ui_notify=get_bool("ui_notify", True),

        bridge_offline_timeout_s=_get_float(s, "bridge_offline_timeout_s", 1.0),
        pump_offline_timeout_s=_get_float(s, "pump_offline_timeout_s", 1.2),

        log_file=_get_str(s, "log_file", os.path.expanduser("~/printer_data/logs/drukmix.log")),
        log_level=_get_str(s, "log_level", "info").lower(),
        log_period_s=_get_float(s, "log_period_s", 5.0),

        flush_burst_count=_get_int(s, "flush_burst_count", 10),
        flush_burst_interval_ms=_get_int(s, "flush_burst_interval_ms", 20),
        flush_confirm=get_bool("flush_confirm", True),
        flush_confirm_timeout_s=_get_float(s, "flush_confirm_timeout_s", 1.2),
        flush_confirm_tolerance_code=_get_int(s, "flush_confirm_tolerance_code", 8),
        flush_confirm_retries=_get_int(s, "flush_confirm_retries", 2),

        cfg_reload_s=_get_float(s, "cfg_reload_s", 2.0),
        cfg_path=path,
    )


def read_filament_diameter_from_printer_cfg(path: str, fallback: float) -> float:
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return fallback
    m = re.search(r"(?ms)^\[extruder\]\s*(.*?)(^\[|\Z)", txt)
    section = m.group(1) if m else txt
    m2 = re.search(r"(?m)^\s*filament_diameter\s*:\s*([0-9]*\.?[0-9]+)\s*$", section)
    if not m2:
        return fallback
    try:
        d = float(m2.group(1))
        return d if d > 0 else fallback
    except Exception:
        return fallback


def liters_per_mm_from_diameter_mm(d: float) -> float:
    r = d / 2.0
    area_mm2 = math.pi * r * r
    return area_mm2 / 1_000_000.0
