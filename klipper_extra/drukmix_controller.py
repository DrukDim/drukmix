# Klipper-side controller for planner-driven pump orchestration.
#
# Contract (get_status):
#   {
#     "state": "idle|prestart|run|prestop|blocked",
#     "target_pct": float,
#     "rev": bool,
#     "reason": str,
#     "t_start_s": Optional[float],
#     "t_stop_s": Optional[float],
#     "v_mms": float,
#     "available": bool,
#     "stale": bool,
#   }
#
# Rules:
# - Lightweight and non-blocking; no I/O in event callbacks.
# - Planner authority comes from drukmix_planner_probe.
# - Transport/backend logic remains host-side.

import logging
import math


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class DrukMixController:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.probe_name = config.get("probe", "drukmix_planner_probe")
        self.extruder_name = config.get("extruder", "extruder")
        self.enabled = config.getboolean("enabled", True)

        # Lookahead / policy
        self.start_lookahead_s = config.getfloat(
            "pump_start_lookahead_s", 4.0, minval=0.0
        )
        self.run_lookahead_s = config.getfloat("pump_run_lookahead_s", 1.0, minval=0.0)
        self.stop_lookahead_s = config.getfloat(
            "pump_stop_lookahead_s", 3.0, minval=0.0
        )
        self.prestart_mode = (
            str(config.get("pump_prestart_mode", "fixed")).strip().lower()
        )
        self.prestart_pct = config.getfloat("pump_prestart_pct", 18.0, minval=0.0)
        self.prestart_min_pct = config.getfloat(
            "pump_prestart_min_pct", 0.0, minval=0.0
        )
        self.prestop_ramp_s = config.getfloat("pump_prestop_ramp_s", 0.0, minval=0.0)
        self.prestop_min_gap_s = config.getfloat(
            "pump_prestop_min_gap_s", 3.0, minval=0.0
        )
        self.planner_stale_timeout_s = config.getfloat(
            "planner_stale_timeout_s", 0.0, minval=0.0
        )

        # Core mapping from velocity -> percent
        self.max_flow_lpm = config.getfloat("max_flow_lpm", 10.0, minval=0.001)
        self.gain_pct = config.getfloat("gain_pct", 100.0, minval=0.0)
        self.min_print_mms = config.getfloat("min_print_mms", 0.0, minval=0.0)
        self.min_flow_pct = config.getfloat("min_flow_pct", 0.0, minval=0.0)
        self.min_flow_hold_s = config.getfloat("min_flow_hold_s", 0.0, minval=0.0)
        self.retract_deadband_mms = config.getfloat(
            "retract_deadband_mms", 0.2, minval=0.0
        )
        self.retract_gain_pct = config.getfloat("retract_gain_pct", 100.0, minval=0.0)
        self.filament_diameter_mm = config.getfloat(
            "filament_diameter_fallback", 35.0, minval=0.001
        )

        self.debug_enabled = config.getboolean("debug_enabled", False)
        self.debug_log_every_s = config.getfloat("debug_log_every_s", 1.0, minval=0.1)

        # Runtime references
        self.probe = None
        self.gcode_move = None
        self._last_status = None
        self._last_log_t = 0.0
        self._min_flow_until = 0.0
        self._last_planner_eventtime = 0.0
        self._last_state = "idle"

        self.liters_per_mm = self._calc_liters_per_mm(self.filament_diameter_mm)

        self.printer.register_event_handler("klippy:connect", self._handle_connect)

    def _calc_liters_per_mm(self, diameter_mm: float) -> float:
        r = max(0.0, diameter_mm) / 2.0
        area_mm2 = math.pi * r * r
        return area_mm2 / 1_000_000.0

    def _handle_connect(self):
        self.probe = self.printer.lookup_object(self.probe_name, None)
        self.gcode_move = self.printer.lookup_object("gcode_move", None)
        logging.info(
            "drukmix_controller connected: probe=%s available=%s",
            self.probe_name,
            self.probe is not None,
        )

    def _planner_status(self, eventtime):
        if self.probe is None:
            return None
        try:
            st = self.probe.get_status(eventtime)
            if st is not None:
                self._last_planner_eventtime = float(eventtime)
            return st
        except Exception:
            logging.exception("drukmix_controller: planner probe status failed")
            return None

    def _planner_is_fresh(self, eventtime) -> bool:
        if self._last_planner_eventtime <= 0.0:
            return False
        timeout = max(0.1, float(self.planner_stale_timeout_s))
        return (float(eventtime) - self._last_planner_eventtime) <= timeout

    def _extrude_factor(self, eventtime) -> float:
        try:
            if self.gcode_move is None:
                return 1.0
            st = self.gcode_move.get_status(eventtime) or {}
            ef = float(st.get("extrude_factor", 1.0))
            return ef if ef > 0 else 1.0
        except Exception:
            return 1.0

    def _core_compute(self, vel_mms: float, ef: float, eventtime: float):
        abs_vel = abs(vel_mms)
        rev = vel_mms < -self.retract_deadband_mms

        if abs_vel < self.min_print_mms:
            return 0.0, False

        lpm = abs_vel * self.liters_per_mm * 60.0
        lpm *= max(ef, 0.0)

        if rev:
            lpm *= self.retract_gain_pct / 100.0
        else:
            lpm *= self.gain_pct / 100.0

        pct = clamp((lpm / self.max_flow_lpm) * 100.0, 0.0, 100.0)

        if (not rev) and self.min_flow_pct > 0.0 and self.min_flow_hold_s > 0.0:
            now = float(eventtime)
            if pct >= self.min_flow_pct:
                self._min_flow_until = now + self.min_flow_hold_s
            elif now < self._min_flow_until:
                pct = max(pct, self.min_flow_pct)

        return pct, rev

    def _prestop_ramp(self, nominal_pct: float, t_stop: float) -> float:
        ramp_s = max(0.0, float(self.prestop_ramp_s))
        if ramp_s <= 0.0:
            return 0.0
        x = clamp(t_stop / ramp_s, 0.0, 1.0)
        return max(0.0, nominal_pct) * x

    def _build_status(
        self,
        *,
        state,
        target_pct,
        rev,
        reason,
        t_start_s,
        t_stop_s,
        v_mms,
        available,
        stale,
    ):
        out = {
            "state": state,
            "target_pct": float(clamp(target_pct, 0.0, 100.0)),
            "rev": bool(rev),
            "reason": str(reason),
            "t_start_s": t_start_s,
            "t_stop_s": t_stop_s,
            "v_mms": float(max(0.0, v_mms)),
            "available": bool(available),
            "stale": bool(stale),
        }
        self._maybe_debug(out)
        self._last_status = out
        return out

    def _maybe_debug(self, st):
        if not self.debug_enabled:
            return
        now = self.reactor.monotonic()
        if (now - self._last_log_t) >= self.debug_log_every_s:
            self._last_log_t = now
            logging.info(
                "drukmix_controller state=%s tgt=%.2f rev=%d reason=%s v_mms=%.3f t_start=%s t_stop=%s available=%d stale=%d",
                st["state"],
                st["target_pct"],
                int(st["rev"]),
                st["reason"],
                st["v_mms"],
                st["t_start_s"],
                st["t_stop_s"],
                int(st["available"]),
                int(st["stale"]),
            )

    def get_status(self, eventtime):
        if not self.enabled:
            return self._build_status(
                state="blocked",
                target_pct=0.0,
                rev=False,
                reason="disabled",
                t_start_s=None,
                t_stop_s=None,
                v_mms=0.0,
                available=False,
                stale=True,
            )
        planner = self._planner_status(eventtime)
        if planner is None:
            return self._build_status(
                state="blocked",
                target_pct=0.0,
                rev=False,
                reason="no_planner",
                t_start_s=None,
                t_stop_s=None,
                v_mms=0.0,
                available=False,
                stale=True,
            )

        available = bool(planner.get("available", False))
        t_start = planner.get("time_to_print_start_s")
        t_stop = planner.get("time_to_print_stop_s")
        control_velocity = float(planner.get("control_velocity_mms", 0.0))
        stale = not self._planner_is_fresh(eventtime)
        active_window = t_stop is not None

        if not available:
            return self._build_status(
                state="blocked",
                target_pct=0.0,
                rev=False,
                reason="planner_unavailable",
                t_start_s=t_start,
                t_stop_s=t_stop,
                v_mms=control_velocity,
                available=False,
                stale=stale,
            )

        ef = self._extrude_factor(eventtime)
        run_pct, run_rev = self._core_compute(control_velocity, ef, eventtime)

        semantic_state = "idle"
        target_pct = 0.0
        rev = False

        if stale:
            semantic_state = "blocked"
            reason = "stale"
        elif active_window:
            # Active window; choose run or prestop.
            if t_stop is not None and t_stop <= self.stop_lookahead_s:
                if t_start is not None and t_start <= self.prestop_min_gap_s:
                    semantic_state = "run"
                    target_pct = run_pct
                    rev = run_rev
                    reason = "run_gap_short"
                else:
                    semantic_state = "prestop"
                    target_pct = self._prestop_ramp(run_pct, t_stop)
                    rev = False
                    reason = "prestop"
            else:
                semantic_state = "run"
                target_pct = run_pct
                rev = run_rev
                reason = "run"
        else:
            # No active window; consider prestart/run_hold or idle.
            if t_start is not None and t_start <= self.start_lookahead_s:
                semantic_state = "prestart"
                if self.prestart_mode == "planned":
                    target_pct = max(run_pct, self.prestart_min_pct)
                    reason = "prestart_planned"
                else:
                    target_pct = self.prestart_pct
                    reason = "prestart_fixed"
                rev = False
            elif (
                self._last_state == "run"
                and t_start is not None
                and t_start <= self.run_lookahead_s
                and run_pct > 0.0
            ):
                semantic_state = "run"
                target_pct = run_pct
                rev = run_rev
                reason = "run_hold_gap"
            else:
                semantic_state = "idle"
                target_pct = 0.0
                rev = False
                reason = "idle"

        self._last_state = semantic_state
        return self._build_status(
            state=semantic_state,
            target_pct=target_pct,
            rev=rev,
            reason=reason,
            t_start_s=t_start,
            t_stop_s=t_stop,
            v_mms=control_velocity,
            available=True,
            stale=stale,
        )


def load_config(config):
    return DrukMixController(config)
