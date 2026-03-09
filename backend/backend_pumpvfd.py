from __future__ import annotations

from backend.pump_backend_base import PumpBackend, PumpStatus
from backend.vfd_faults import get_vfd_fault_info


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class PumpVfdBackend(PumpBackend):
    name = "pumpvfd"

    def __init__(self, transport):
        self.transport = transport
        self._auto_reset_err16_done = False
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
                fault_display="LINK",
                fault_name="Bridge status unavailable",
                fault_text="Bridge status unavailable",
                possible_causes=["USB/bridge status is not being received"],
                solutions=["Check bridge power", "Check USB link", "Check agent serial port"],
                can_auto_reset=False,
                auto_reset_attempted=self._auto_reset_err16_done,
                pause_print=True,
                severity="fault",
                target_pct=self._last_target_pct,
                applied_pct=None,
                telemetry_ok=False,
                age_ms=None,
            )

        fault_code = int(raw.get("fault_code", 0))
        info = get_vfd_fault_info(fault_code) if fault_code > 0 else None

        return PumpStatus(
            backend=self.name,
            link_ok=bool(raw.get("link_ok", True)),
            control_mode=str(raw.get("control_mode", "UNKNOWN")),
            running=raw.get("running"),
            rev_active=raw.get("rev_active"),
            faulted=bool(raw.get("faulted", False)),
            fault_code=fault_code,
            fault_display=(info.display if info else ""),
            fault_name=(info.name if info else ""),
            fault_text=(f"{info.display} {info.name}" if info else (f"Err{fault_code:02d}" if fault_code > 0 else "")),
            possible_causes=(list(info.possible_causes) if info else []),
            solutions=(list(info.solutions) if info else []),
            can_auto_reset=bool(info.auto_reset_once) if info else False,
            auto_reset_attempted=self._auto_reset_err16_done,
            pause_print=bool(info.pause_print) if info else False,
            severity=(info.severity if info else ""),
            target_pct=self._last_target_pct,
            applied_pct=raw.get("applied_pct"),
            telemetry_ok=True,
            age_ms=raw.get("age_ms"),
        )

    def maybe_auto_reset_startup_fault(self, printing: bool, running: bool | None) -> bool:
        st = self.poll_status()
        if st.fault_code != 16:
            return False
        if self._auto_reset_err16_done:
            return False
        if printing:
            return False
        if running:
            return False
        self.reset_fault()
        self._auto_reset_err16_done = True
        return True
