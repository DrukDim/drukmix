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

import configparser
import logging
import math
import os
import re


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class DrukMixController:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")
        self.probe_name = config.get("probe", "drukmix_planner_probe")
        self.extruder_name = config.get("extruder", "extruder")
        self.enabled = config.getboolean("enabled", True)
        self.runtime_cfg_path = os.path.expanduser(
            config.get(
                "runtime_cfg_path",
                os.path.expanduser("~/printer_data/config/drukmix_controller.cfg"),
            )
        )

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

        self._boot_tuning = {
            "gain_pct": self.gain_pct,
            "max_flow_lpm": self.max_flow_lpm,
            "pump_start_lookahead_s": self.start_lookahead_s,
            "pump_stop_lookahead_s": self.stop_lookahead_s,
        }

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
        self.gcode.register_command("SET_DRUKMIX_GAIN", self.cmd_DRUKMIX_GAIN)
        self.gcode.register_command("SET_DRUKMIX_LPM", self.cmd_DRUKMIX_LPM)
        self.gcode.register_command("SET_DRUKMIX_PRESTART", self.cmd_DRUKMIX_PRESTART)
        self.gcode.register_command("SET_DRUKMIX_PRESTOP", self.cmd_DRUKMIX_PRESTOP)
        self.gcode.register_command("SET_DRUKMIX_SAVE", self.cmd_DRUKMIX_SAVE)
        self.gcode.register_command("SET_DRUKMIX_RESET", self.cmd_DRUKMIX_RESET)

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
            "gain_pct": float(self.gain_pct),
            "max_flow_lpm": float(self.max_flow_lpm),
            "pump_start_lookahead_s": float(self.start_lookahead_s),
            "pump_stop_lookahead_s": float(self.stop_lookahead_s),
        }
        self._maybe_debug(out)
        self._last_status = out
        return out

    def _set_runtime_tuning(
        self,
        *,
        gain_pct=None,
        max_flow_lpm=None,
        pump_start_lookahead_s=None,
        pump_stop_lookahead_s=None,
    ):
        if gain_pct is not None:
            self.gain_pct = clamp(float(gain_pct), 0.0, 300.0)
        if max_flow_lpm is not None:
            self.max_flow_lpm = max(0.001, float(max_flow_lpm))
        if pump_start_lookahead_s is not None:
            self.start_lookahead_s = max(0.0, float(pump_start_lookahead_s))
        if pump_stop_lookahead_s is not None:
            self.stop_lookahead_s = max(0.0, float(pump_stop_lookahead_s))

    def _read_saved_tuning(self):
        cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        if not cp.read(self.runtime_cfg_path):
            return dict(self._boot_tuning)
        if "drukmix_controller" not in cp:
            return dict(self._boot_tuning)
        s = cp["drukmix_controller"]
        return {
            "gain_pct": s.getfloat("gain_pct", fallback=self._boot_tuning["gain_pct"]),
            "max_flow_lpm": s.getfloat(
                "max_flow_lpm", fallback=self._boot_tuning["max_flow_lpm"]
            ),
            "pump_start_lookahead_s": s.getfloat(
                "pump_start_lookahead_s",
                fallback=self._boot_tuning["pump_start_lookahead_s"],
            ),
            "pump_stop_lookahead_s": s.getfloat(
                "pump_stop_lookahead_s",
                fallback=self._boot_tuning["pump_stop_lookahead_s"],
            ),
        }

    def _write_saved_tuning(self):
        keys = {
            "gain_pct": f"{self.gain_pct:.3f}",
            "max_flow_lpm": f"{self.max_flow_lpm:.3f}",
            "pump_start_lookahead_s": f"{self.start_lookahead_s:.3f}",
            "pump_stop_lookahead_s": f"{self.stop_lookahead_s:.3f}",
        }
        with open(self.runtime_cfg_path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()

        section_start = None
        section_end = len(lines)
        section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
        for idx, line in enumerate(lines):
            m = section_re.match(line)
            if not m:
                continue
            if m.group(1).strip().lower() == "drukmix_controller":
                section_start = idx
                continue
            if section_start is not None:
                section_end = idx
                break
        if section_start is None:
            raise RuntimeError(
                f"[drukmix_controller] section not found in {self.runtime_cfg_path}"
            )

        for key, value in keys.items():
            key_re = re.compile(rf"^(\s*{re.escape(key)}\s*[:=]\s*)([^#;\n]*)(.*)$")
            replaced = False
            for idx in range(section_start + 1, section_end):
                line = lines[idx]
                m = key_re.match(line)
                if not m:
                    continue
                lines[idx] = f"{m.group(1)}{value}{m.group(3)}\n"
                replaced = True
                break
            if not replaced:
                lines.insert(section_end, f"{key}: {value}\n")
                section_end += 1

        with open(self.runtime_cfg_path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)

    def cmd_DRUKMIX_GAIN(self, gcmd):
        pct = gcmd.get_float("PCT", minval=0.0, maxval=300.0)
        self._set_runtime_tuning(gain_pct=pct)
        gcmd.respond_info(f"DrukMix: gain_pct={self.gain_pct:.1f}")

    def cmd_DRUKMIX_LPM(self, gcmd):
        lpm = gcmd.get_float("LPM", minval=0.001)
        self._set_runtime_tuning(max_flow_lpm=lpm)
        gcmd.respond_info(f"DrukMix: max_flow_lpm={self.max_flow_lpm:.3f}")

    def cmd_DRUKMIX_PRESTART(self, gcmd):
        sec = gcmd.get_float("SEC", minval=0.0)
        self._set_runtime_tuning(pump_start_lookahead_s=sec)
        gcmd.respond_info(
            f"DrukMix: pump_start_lookahead_s={self.start_lookahead_s:.3f}"
        )

    def cmd_DRUKMIX_PRESTOP(self, gcmd):
        sec = gcmd.get_float("SEC", minval=0.0)
        self._set_runtime_tuning(pump_stop_lookahead_s=sec)
        gcmd.respond_info(f"DrukMix: pump_stop_lookahead_s={self.stop_lookahead_s:.3f}")

    def cmd_DRUKMIX_SAVE(self, gcmd):
        self._write_saved_tuning()
        gcmd.respond_info(
            "DrukMix: saved gain/lpm/prestart/prestop to drukmix_controller.cfg"
        )

    def cmd_DRUKMIX_RESET(self, gcmd):
        saved = self._read_saved_tuning()
        self._set_runtime_tuning(**saved)
        gcmd.respond_info("DrukMix: reset to saved gain/lpm/prestart/prestop values")

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
