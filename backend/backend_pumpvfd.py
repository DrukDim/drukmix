from __future__ import annotations

import logging

from backend.pump_backend_base import PumpBackend, PumpStatus
from backend.vfd_faults import get_vfd_fault_info


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class PumpVfdBackend(PumpBackend):
    name = "pumpvfd"

    def __init__(self, transport):
        self.transport = transport
        self._auto_reset_err16_done = False
        self._err16_active = False
        self._last_target_pct = 0.0
        self._last_rev = False
        self._stopped = True
        self.debug_log = False

    def open(self) -> None:
        self.transport.open()
        self._stopped = True

    def close(self) -> None:
        self.transport.close()

    def set_auto_target_pct(self, pct: float, rev: bool) -> None:
        pct = clamp(float(pct), 0.0, 100.0)
        rev = bool(rev)

        prev_pct = self._last_target_pct
        prev_rev = self._last_rev
        prev_stopped = self._stopped

        self._last_target_pct = pct
        self._last_rev = rev

        if self.debug_log:
            logging.info(
                "drukmix backend apply: cmd=set_auto_target_pct pct=%.3f rev=%d prev_pct=%.3f prev_rev=%d prev_stopped=%d",
                pct,
                int(rev),
                prev_pct,
                int(prev_rev),
                int(prev_stopped),
            )

        # zero-flow: не спамимо STOP кожен цикл
        if pct <= 0.0:
            if not self._stopped:
                if self.debug_log:
                    logging.info(
                        "drukmix backend apply: action=vfd_stop reason=zero_pct"
                    )
                self.transport.vfd_stop()
                self._stopped = True
            else:
                if self.debug_log:
                    logging.info(
                        "drukmix backend apply: action=skip_stop reason=already_stopped"
                    )
            return

        if self.debug_log:
            logging.info(
                "drukmix backend apply: action=vfd_set_run pct=%.3f rev=%d",
                pct,
                int(rev),
            )
        self.transport.vfd_set_run(pct=pct, rev=rev)
        self._stopped = False

    def stop(self) -> None:
        self._last_target_pct = 0.0
        if self.debug_log:
            logging.info(
                "drukmix backend stop: called last_rev=%d already_stopped=%d",
                int(self._last_rev),
                int(self._stopped),
            )
        if not self._stopped:
            if self.debug_log:
                logging.info("drukmix backend stop: action=vfd_stop")
            self.transport.vfd_stop()
            self._stopped = True

    def reset_fault(self) -> None:
        self.transport.vfd_reset_fault()
        self._auto_reset_err16_done = False

    def poll_status(self) -> PumpStatus:
        raw = self.transport.read_status(allow_cached=False)
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
                solutions=[
                    "Check bridge power",
                    "Check USB link",
                    "Check driver serial port",
                ],
                can_auto_reset=False,
                auto_reset_attempted=self._auto_reset_err16_done,
                pause_print=True,
                severity="fault",
                target_pct=self._last_target_pct,
                telemetry_ok=False,
                age_ms=None,
            )

        fault_code = int(raw.get("fault_code", 0))

        if fault_code == 16:
            if not self._err16_active:
                self._auto_reset_err16_done = False
            self._err16_active = True
        else:
            self._err16_active = False
            self._auto_reset_err16_done = False

        if self.debug_log:
            logging.info(
                "drukmix backend poll: link_ok=%s running=%s rev_active=%s faulted=%s code=%s target_pct=%.3f target_mlpm=%s hw_raw=%s pump_flags=%s ack_seq=%s applied=%s age_ms=%s",
                raw.get("link_ok"),
                raw.get("running"),
                raw.get("rev_active"),
                raw.get("faulted"),
                fault_code,
                self._last_target_pct,
                raw.get("target_milli_lpm"),
                raw.get("hw_setpoint_raw"),
                raw.get("pump_flags"),
                raw.get("last_ack_seq"),
                raw.get("applied_code"),
                raw.get("age_ms"),
            )

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
            fault_text=(
                f"{info.display} {info.name}"
                if info
                else (f"Err{fault_code:02d}" if fault_code > 0 else "")
            ),
            possible_causes=(list(info.possible_causes) if info else []),
            solutions=(list(info.solutions) if info else []),
            can_auto_reset=bool(info.auto_reset_once) if info else False,
            auto_reset_attempted=self._auto_reset_err16_done,
            pause_print=bool(info.pause_print) if info else False,
            severity=(info.severity if info else ""),
            target_pct=self._last_target_pct,
            telemetry_ok=True,
            age_ms=raw.get("age_ms"),
            target_milli_lpm=int(raw.get("target_milli_lpm", -1)),
            hw_setpoint_raw=int(raw.get("hw_setpoint_raw", -1)),
            pump_flags=int(raw.get("pump_flags", -1)),
            pump_mode=int(raw.get("pump_mode", -1)),
            last_ack_seq=int(raw.get("last_ack_seq", -1)),
            applied_code=int(raw.get("applied_code", -1)),
        )

    def maybe_auto_reset_startup_fault(
        self, printing: bool, running: bool | None
    ) -> bool:
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
