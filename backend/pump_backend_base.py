from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PumpStatus:
    backend: str
    link_ok: bool
    control_mode: str
    running: Optional[bool]
    rev_active: Optional[bool]
    faulted: bool
    fault_code: int

    fault_display: str = ""
    fault_name: str = ""
    fault_text: str = ""
    possible_causes: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)
    can_auto_reset: bool = False
    auto_reset_attempted: bool = False

    target_pct: Optional[float] = None
    applied_pct: Optional[float] = None
    telemetry_ok: bool = False
    age_ms: Optional[int] = None


class PumpBackend:
    name = "base"

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def set_auto_target_pct(self, pct: float, rev: bool) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def reset_fault(self) -> None:
        raise NotImplementedError

    def poll_status(self) -> PumpStatus:
        raise NotImplementedError
