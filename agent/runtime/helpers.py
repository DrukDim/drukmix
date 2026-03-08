from __future__ import annotations
from typing import Dict, Optional, Tuple

EF_MANUAL_FWD = 0x0010
EF_MANUAL_REV = 0x0020
EF_AUTO_ALLOWED = 0x0040
EF_AUTO_ACTIVE = 0x0080
EF_DIR_ASSERTED = 0x0100
EF_WIPER_TPL = 0x0200


def apply_status(ks, st: Dict[str, object]) -> None:
    if "print_stats" in st and "state" in st["print_stats"]:
        ks.print_state = str(st["print_stats"]["state"])
    if "idle_timeout" in st and "state" in st["idle_timeout"]:
        ks.idle_state = str(st["idle_timeout"]["state"])
    if "pause_resume" in st and "is_paused" in st["pause_resume"]:
        ks.is_paused = bool(st["pause_resume"]["is_paused"])

    if "webhooks" in st and "state" in st["webhooks"]:
        ks.klippy_state = str(st["webhooks"]["state"])
    if "gcode_move" in st and "extrude_factor" in st["gcode_move"]:
        try:
            ks.extrude_factor = float(st["gcode_move"]["extrude_factor"])
        except Exception:
            ks.extrude_factor = 1.0
    if "motion_report" in st and "live_extruder_velocity" in st["motion_report"]:
        try:
            ks.live_extruder_velocity = float(st["motion_report"]["live_extruder_velocity"])
        except Exception:
            ks.live_extruder_velocity = 0.0


def is_printing(ks) -> bool:
    ps = ks.print_state.lower()
    it = ks.idle_state.lower()
    return (ps == "printing") or (it == "printing")


def parse_remote_call(msg: dict) -> Optional[Tuple[str, dict]]:
    m = msg.get("method")
    if not isinstance(m, str) or not m.startswith("drukmix_"):
        return None
    p = msg.get("params") or {}
    return (m, p) if isinstance(p, dict) else (m, {})


def decode_mode(err_flags: int) -> str:
    if err_flags & EF_MANUAL_FWD:
        return "MANUAL_FWD"
    if err_flags & EF_MANUAL_REV:
        return "MANUAL_REV"
    return "AUTO"
