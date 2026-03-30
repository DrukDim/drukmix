from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

PUMP_FLAG_RUNNING = 1 << 0
PUMP_FLAG_FORWARD = 1 << 1
PUMP_FLAG_REVERSE = 1 << 2
PUMP_FLAG_MANUAL_MODE = 1 << 3
PUMP_FLAG_REMOTE_MODE = 1 << 4
PUMP_FLAG_FAULT_LATCHED = 1 << 5
PUMP_FLAG_WDOG_STOP = 1 << 6
PUMP_FLAG_HW_READY = 1 << 7


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class PumpModel:
    pump_max_milli_lpm: int = 10000
    target_milli_lpm: int = 0
    applied_milli_lpm: float = 0.0
    rev: bool = False
    link_ok: bool = True
    last_seen_mono_s: float = 0.0
    last_cmd_mono_s: float = 0.0
    last_ack_seq: int = 0
    applied_code: int = 0


class FakeBridgeTransport:
    """
    Deterministic fake transport for tests.

    - No PTY / serial device.
    - Records set_flow events to JSONL for audit scripts.
    - Provides a minimal status dict compatible with backends.
    """

    def __init__(
        self,
        log_jsonl: Optional[str] = None,
        max_lpm: float = 10.0,
        tau_up_s: float = 1.0,
        tau_down_s: float = 0.8,
        running_threshold_pct: float = 2.0,
    ):
        self.log_jsonl = log_jsonl
        self.model = PumpModel(pump_max_milli_lpm=max(1000, int(max_lpm * 1000.0)))
        self.tau_up_s = max(1e-6, float(tau_up_s))
        self.tau_down_s = max(1e-6, float(tau_down_s))
        self.running_threshold_pct = max(0.0, float(running_threshold_pct))
        self._last_status: Optional[dict] = None
        self._last_status_monotonic: float = 0.0

    def open(self):
        now = time.monotonic()
        self.model.last_seen_mono_s = now
        self.model.last_cmd_mono_s = now

    def close(self):
        pass

    def invalidate_status_cache(self):
        self._last_status = None
        self._last_status_monotonic = 0.0

    def _log(self, event: str, **data):
        if not self.log_jsonl:
            return
        row = {"ts_mono": time.monotonic(), "event": event, **data}
        with open(self.log_jsonl, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(row, ensure_ascii=True) + "\n")

    def _tick(self):
        now = time.monotonic()
        dt = max(0.0, now - self.model.last_seen_mono_s)
        self.model.last_seen_mono_s = now

        target = float(self.model.target_milli_lpm)
        applied = float(self.model.applied_milli_lpm)
        tau = self.tau_up_s if target >= applied else self.tau_down_s
        alpha = 1.0 - pow(2.718281828459045, -dt / tau)
        self.model.applied_milli_lpm = applied + (target - applied) * alpha

    def _flags(self) -> int:
        flags = PUMP_FLAG_HW_READY | PUMP_FLAG_REMOTE_MODE
        running_threshold = (
            self.running_threshold_pct / 100.0
        ) * self.model.pump_max_milli_lpm
        if self.model.applied_milli_lpm >= running_threshold:
            flags |= PUMP_FLAG_RUNNING
        if self.model.rev:
            flags |= PUMP_FLAG_REVERSE
        elif self.model.target_milli_lpm > 0:
            flags |= PUMP_FLAG_FORWARD
        return flags

    def read_status(self, allow_cached: bool = False, max_cache_age_s: float = 0.0):
        now = time.monotonic()
        if (
            allow_cached
            and self._last_status is not None
            and max_cache_age_s > 0.0
            and (now - self._last_status_monotonic) <= max_cache_age_s
        ):
            return dict(self._last_status)

        self._tick()

        age_ms = int(max(0.0, now - self.model.last_cmd_mono_s) * 1000.0)
        running_threshold = (
            self.running_threshold_pct / 100.0
        ) * self.model.pump_max_milli_lpm
        running = self.model.applied_milli_lpm >= running_threshold

        st = {
            "link_ok": self.model.link_ok,
            "control_mode": "AUTO",
            "pump_mode": 3,
            "running": bool(running),
            "rev_active": bool(self.model.rev),
            "faulted": False,
            "fault_code": 0,
            "age_ms": age_ms,
            "target_milli_lpm": int(self.model.target_milli_lpm),
            "hw_setpoint_raw": int(self.model.target_milli_lpm),
            "pump_flags": int(self._flags()),
            "last_ack_seq": int(self.model.last_ack_seq),
            "applied_code": int(self.model.applied_code),
        }
        self._last_status = dict(st)
        self._last_status_monotonic = now
        return st

    def _apply_flow(self, target_milli_lpm: int, rev: bool):
        self.model.target_milli_lpm = int(
            _clamp(target_milli_lpm, 0, self.model.pump_max_milli_lpm)
        )
        self.model.rev = bool(rev)
        self.model.last_ack_seq = (self.model.last_ack_seq + 1) & 0xFFFF
        self.model.applied_code = 0
        self.model.last_cmd_mono_s = time.monotonic()
        self.invalidate_status_cache()
        self._log(
            "set_flow",
            target_milli_lpm=int(self.model.target_milli_lpm),
            rev=bool(self.model.rev),
            mode="AUTO",
        )

    def vfd_set_run(self, pct: float, rev: bool):
        target_milli_lpm = int(
            _clamp(pct, 0.0, 100.0) * self.model.pump_max_milli_lpm / 100.0
        )
        self._apply_flow(target_milli_lpm, rev)

    def vfd_stop(self):
        self._apply_flow(0, False)

    def vfd_reset_fault(self):
        self.model.applied_code = 0
        self.model.last_cmd_mono_s = time.monotonic()
        self.invalidate_status_cache()
        self._log("reset_fault")
