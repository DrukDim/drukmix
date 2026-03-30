from __future__ import annotations

from backend.pump_backend_base import PumpBackend, PumpStatus


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class PumpTplBackend(PumpBackend):
    name = "pumptpl"

    def __init__(self, transport):
        self.transport = transport
        self._last_target_pct = 0.0
        self._last_rev = False

    def open(self) -> None:
        self.transport.open()

    def close(self) -> None:
        self.transport.close()

    def set_auto_target_pct(self, pct: float, rev: bool) -> None:
        pct = clamp(float(pct), 0.0, 100.0)
        self._last_target_pct = pct
        self._last_rev = bool(rev)
        self.transport.tpl_set_auto(pct=pct, rev=rev)

    def stop(self) -> None:
        self._last_target_pct = 0.0
        self.transport.tpl_stop()

    def reset_fault(self) -> None:
        pass

    def poll_status(self) -> PumpStatus:
        raw = self.transport.read_status()
        if raw is None:
            return PumpStatus(
                backend=self.name,
                link_ok=False,
                control_mode="UNKNOWN",
                running=None,
                rev_active=None,
                faulted=True,
                fault_code=-1,
                target_pct=self._last_target_pct,
                telemetry_ok=False,
                age_ms=None,
            )

        return PumpStatus(
            backend=self.name,
            link_ok=bool(raw.get("link_ok", True)),
            control_mode=raw.get("control_mode", "UNKNOWN"),
            running=None,
            rev_active=raw.get("rev_active"),
            faulted=False,
            fault_code=0,
            target_pct=self._last_target_pct,
            telemetry_ok=False,
            age_ms=raw.get("age_ms"),
            pump_mode=int(raw.get("pump_mode", -1)),
        )
