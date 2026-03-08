from __future__ import annotations

from agent.runtime.config import clamp
from agent.runtime.transport import FLAG_AUTO, FLAG_REV, FLAG_STOP


def expected_code(lpm: float, max_lpm: float) -> int:
    if max_lpm <= 0:
        return 0
    c = int(round((clamp(lpm, 0.0, max_lpm) / max_lpm) * 255.0))
    return int(clamp(c, 0, 255))


def compute_desired_flow(
    *,
    flush_active: bool,
    flush_lpm: float,
    active_motion: bool,
    mode: str,
    live_extruder_velocity: float,
    extrude_factor: float,
    liters_per_mm: float,
    max_lpm: float,
    gain: float,
    retract_deadband_mm_s: float,
    retract_gain: float,
    min_run_lpm: float,
):
    if flush_active:
        desired_lpm = clamp(flush_lpm, 0.0, max_lpm)
        flags = FLAG_AUTO if desired_lpm > 0.0 else FLAG_STOP
        return desired_lpm, flags

    if (not active_motion) or (mode != "AUTO"):
        return 0.0, FLAG_STOP

    vel = float(live_extruder_velocity)
    dead = max(0.0, retract_deadband_mm_s)
    is_rev = vel < -dead

    speed = abs(vel)
    lpm = speed * liters_per_mm * 60.0
    lpm *= max(0.0, float(extrude_factor))
    lpm *= max(0.0, (retract_gain if is_rev else gain))
    lpm = clamp(lpm, 0.0, max_lpm)

    if not is_rev:
        if 0.0 < lpm < min_run_lpm:
            lpm = min_run_lpm

    desired_lpm = lpm
    if desired_lpm <= 0.0:
        flags = FLAG_STOP
    else:
        flags = FLAG_AUTO | (FLAG_REV if is_rev else 0)

    return desired_lpm, flags
