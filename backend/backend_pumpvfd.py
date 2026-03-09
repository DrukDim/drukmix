from __future__ import annotations

from backend.pump_backend_base import PumpBackend, PumpStatus


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class PumpVfdBackend(PumpBackend):
    name = "pumpvfd"

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

        if pct <= 0.0:
            self.stop()
            return

        self.transport.vfd_set_run(pct=pct, rev=rev)

    def stop(self) -> None:
        self._last_target_pct = 0.0
        self.transport.vfd_stop()

    def reset_fault(self) -> None:
        self.transport.vfd_reset_fault()

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
                applied_pct=None,
                telemetry_ok=False,
                age_ms=None,
            )

        return PumpStatus(
            backend=self.name,
            link_ok=bool(raw.get("link_ok", True)),
            control_mode=raw.get("control_mode", "UNKNOWN"),
            running=raw.get("running"),
            rev_active=raw.get("rev_active"),
            faulted=bool(raw.get("faulted", False)),
            fault_code=int(raw.get("fault_code", 0)),
            target_pct=self._last_target_pct,
            applied_pct=raw.get("applied_pct"),
            telemetry_ok=True,
            age_ms=raw.get("age_ms"),
        )
