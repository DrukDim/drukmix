from __future__ import annotations
import dataclasses
from typing import Optional


@dataclasses.dataclass
class KlipperState:
    print_state: str = "unknown"
    idle_state: str = "unknown"
    is_paused: bool = False
    klippy_state: str = "unknown"
    extrude_factor: float = 1.0
    live_extruder_velocity: float = 0.0


@dataclasses.dataclass
class LinkState:
    last_bridge_frame_t: float = 0.0
    pump_link: int = 0
    age_ms: Optional[int] = None
    last_code: int = 0
    err_flags: int = 0


@dataclasses.dataclass
class FlushState:
    active: bool = False
    lpm: float = 0.0
    until_t: float = 0.0


@dataclasses.dataclass
class Overrides:
    gain: float | None = None
    log_level: str | None = None
