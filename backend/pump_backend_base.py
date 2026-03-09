from __future__ import annotations

from dataclasses import dataclass
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
    target_pct: Optional[float]
    applied_pct: Optional[float]
    telemetry_ok: bool
    age_ms: Optional[int]


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
