from __future__ import annotations

from dataclasses import dataclass


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class CoreSettings:
    max_flow_lpm: float = 10.0
    gain_pct: float = 100.0
    min_print_mms: float = 0.0
    min_flow_pct: float = 0.0
    min_flow_hold_s: float = 0.0
    retract_deadband_mms: float = 0.2
    retract_gain_pct: float = 100.0


@dataclass
class CoreInput:
    printing: bool
    paused: bool
    live_extruder_velocity: float
    extrude_factor: float
    liters_per_mm: float


@dataclass
class CoreOutput:
    target_pct: float
    rev: bool
    stop: bool
    reason: str


class DrukMixCore:
    def __init__(self, cfg: CoreSettings):
        self.cfg = cfg
        self._min_flow_until = 0.0

    def _lpm_to_pct(self, lpm: float) -> float:
        max_flow = max(self.cfg.max_flow_lpm, 0.001)
        return clamp((lpm / max_flow) * 100.0, 0.0, 100.0)

    def compute(self, inp: CoreInput, now: float) -> CoreOutput:
        if not inp.printing or inp.paused:
            return CoreOutput(0.0, False, True, "not_printing_or_paused")

        vel = float(inp.live_extruder_velocity)
        abs_vel = abs(vel)
        rev = vel < -max(0.0, self.cfg.retract_deadband_mms)

        if abs_vel < max(0.0, self.cfg.min_print_mms):
            return CoreOutput(0.0, False, True, "below_min_print_speed")

        lpm = abs_vel * inp.liters_per_mm * 60.0
        lpm *= max(0.0, inp.extrude_factor)

        if rev:
            lpm *= max(0.0, self.cfg.retract_gain_pct) / 100.0
        else:
            lpm *= max(0.0, self.cfg.gain_pct) / 100.0

        pct = self._lpm_to_pct(lpm)

        min_flow_pct = clamp(self.cfg.min_flow_pct, 0.0, 100.0)
        if (not rev) and min_flow_pct > 0.0 and self.cfg.min_flow_hold_s > 0.0:
            if pct >= min_flow_pct:
                self._min_flow_until = now + self.cfg.min_flow_hold_s
            elif now < self._min_flow_until:
                pct = max(pct, min_flow_pct)

        if pct <= 0.0:
            return CoreOutput(0.0, False, True, "zero_pct")

        return CoreOutput(pct, rev, False, "ok")
