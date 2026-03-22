#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import configparser
import dataclasses
import json
import logging
import math
import os
import re
import time
import fcntl
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

import websockets

from backend.agent_core_logic import CoreInput, CoreSettings, DrukMixCore
from backend.backend_pumpvfd import PumpVfdBackend
from backend.bridge_usb_transport import BridgeUsbTransport
from backend.backend_pumptpl import PumpTplBackend


PLANNER_FIELD_NAMES = [
    "queue_tail_s",
    "print_window_active",
    "time_to_print_start_s",
    "time_to_print_stop_s",
    "control_velocity_mms",
]


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclasses.dataclass
class Cfg:
    enabled: bool
    moonraker_ws: str
    backend: str
    serial_port: str
    serial_baud: int

    client_name: str
    client_version: str
    client_type: str
    client_url: str

    printer_cfg: str
    filament_diameter_fallback: float

    max_flow_lpm: float
    gain_pct: float
    min_print_mms: float
    min_flow_pct: float
    min_flow_hold_s: float
    retract_deadband_mms: float
    retract_gain_pct: float
    pump_start_lookahead_s: float
    pump_run_lookahead_s: float
    pump_stop_lookahead_s: float
    pump_prestart_pct: float
    pump_prestop_ramp_s: float
    planner_stale_timeout_s: float

    update_hz: float
    log_period_s: float

    pause_on_pump_offline: bool
    pause_on_manual_mode: bool
    ui_notify: bool
    planner_debug_log: bool
    backend_debug_log: bool
    pump_offline_timeout_s: float

    log_file: str
    log_level: str
    cfg_reload_s: float
    cfg_path: str = ""


@dataclasses.dataclass
class KlipperState:
    extrude_factor: float = 1.0
    planner_queue_tail_s: float = 0.0
    planner_print_window_active: bool = False
    planner_time_to_print_start_s: Optional[float] = None
    planner_time_to_print_stop_s: Optional[float] = None
    planner_control_velocity_mms: float = 0.0
    planner_last_update_t: float = 0.0


@dataclasses.dataclass
class FlushState:
    active: bool = False
    pct: float = 0.0
    until_t: float = 0.0


def _strip_inline_comment(v: str) -> str:
    if v is None:
        return ""
    v = str(v)
    v = v.split("#", 1)[0]
    v = v.split(";", 1)[0]
    return v.strip()


def _get_str(s: configparser.SectionProxy, key: str, default: str) -> str:
    return _strip_inline_comment(s.get(key, default))


def _get_int(s: configparser.SectionProxy, key: str, default: int) -> int:
    raw = s.get(key, str(default))
    return int(float(_strip_inline_comment(raw)))


def _get_float(s: configparser.SectionProxy, key: str, default: float) -> float:
    raw = s.get(key, str(default))
    return float(_strip_inline_comment(raw))


def load_config(path: str) -> Cfg:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cp.read(path):
        raise FileNotFoundError(path)
    s = cp["drukmix"]

    def get_bool(k: str, d: bool = False) -> bool:
        raw = _strip_inline_comment(s.get(k, str(d))).lower()
        return raw in ("1", "true", "yes", "on")

    return Cfg(
        enabled=get_bool("enabled", True),
        moonraker_ws=_get_str(s, "moonraker_ws", "ws://127.0.0.1:7125/websocket"),
        backend=_get_str(s, "backend", "pumpvfd"),
        serial_port=_get_str(s, "serial_port", ""),
        serial_baud=_get_int(s, "serial_baud", 921600),

        client_name=_get_str(s, "client_name", "drukmix"),
        client_version=_get_str(s, "client_version", "4.0.0"),
        client_type=_get_str(s, "client_type", "agent"),
        client_url=_get_str(s, "client_url", "https://drukos.local/drukmix"),

        printer_cfg=_get_str(s, "printer_cfg", os.path.expanduser("~/printer_data/config/printer.cfg")),
        filament_diameter_fallback=_get_float(s, "filament_diameter_fallback", 35.0),

        max_flow_lpm=_get_float(s, "max_flow_lpm", 10.0),
        gain_pct=_get_float(s, "gain_pct", 100.0),
        min_print_mms=_get_float(s, "min_print_mms", 0.0),
        min_flow_pct=_get_float(s, "min_flow_pct", 0.0),
        min_flow_hold_s=_get_float(s, "min_flow_hold_s", 0.0),
        retract_deadband_mms=_get_float(s, "retract_deadband_mms", 0.20),
        retract_gain_pct=_get_float(s, "retract_gain_pct", 100.0),
        pump_start_lookahead_s=_get_float(s, "pump_start_lookahead_s", 4.0),
        pump_run_lookahead_s=_get_float(s, "pump_run_lookahead_s", 1.0),
        pump_stop_lookahead_s=_get_float(s, "pump_stop_lookahead_s", 3.0),
        pump_prestart_pct=_get_float(s, "pump_prestart_pct", 18.0),
        pump_prestop_ramp_s=_get_float(s, "pump_prestop_ramp_s", 3.0),
        planner_stale_timeout_s=_get_float(s, "planner_stale_timeout_s", 1.5),

        update_hz=_get_float(s, "update_hz", 6.0),
        log_period_s=_get_float(s, "log_period_s", 5.0),

        pause_on_pump_offline=get_bool("pause_on_pump_offline", True),
        pause_on_manual_mode=get_bool("pause_on_manual_mode", True),
        ui_notify=get_bool("ui_notify", True),
        planner_debug_log=get_bool("planner_debug_log", False),
        backend_debug_log=get_bool("backend_debug_log", False),

        pump_offline_timeout_s=_get_float(s, "pump_offline_timeout_s", 1.2),

        log_file=_get_str(s, "log_file", os.path.expanduser("~/printer_data/logs/drukmix.log")),
        log_level=_get_str(s, "log_level", "info").lower(),

        cfg_reload_s=_get_float(s, "cfg_reload_s", 2.0),
        cfg_path=path,
    )


def setup_logger(log_file: str, log_level: str = "info") -> logging.Logger:
    lg = logging.getLogger("drukmix")
    level_name = str(log_level or "info").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    lg.setLevel(level)
    lg.handlers.clear()

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    fh.setLevel(level)
    lg.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(level)
    lg.addHandler(sh)
    return lg


def read_filament_diameter_from_printer_cfg(path: str, fallback: float) -> float:
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return fallback
    m = re.search(r"(?ms)^\[extruder\]\s*(.*?)(^\[|\Z)", txt)
    section = m.group(1) if m else txt
    m2 = re.search(r"(?m)^\s*filament_diameter\s*=\s*([0-9]*\.?[0-9]+)\s*$", section)
    if not m2:
        m2 = re.search(r"(?m)^\s*filament_diameter\s*:\s*([0-9]*\.?[0-9]+)\s*$", section)
    if not m2:
        return fallback
    try:
        d = float(m2.group(1))
        return d if d > 0 else fallback
    except Exception:
        return fallback


def liters_per_mm_from_diameter_mm(d: float) -> float:
    r = d / 2.0
    area_mm2 = math.pi * r * r
    return area_mm2 / 1_000_000.0


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def apply_status(ks: KlipperState, st: Dict[str, Any], now: float) -> None:
    if "gcode_move" in st and "extrude_factor" in st["gcode_move"]:
        try:
            ks.extrude_factor = float(st["gcode_move"]["extrude_factor"])
        except Exception:
            ks.extrude_factor = 1.0

    if "drukmix_planner_probe" in st and isinstance(st["drukmix_planner_probe"], dict):
        pp = st["drukmix_planner_probe"]

        if "queue_tail_s" in pp:
            ks.planner_queue_tail_s = _safe_float(pp.get("queue_tail_s"), 0.0)
        if "print_window_active" in pp:
            ks.planner_print_window_active = bool(pp.get("print_window_active"))
        if "time_to_print_start_s" in pp:
            v = pp.get("time_to_print_start_s")
            ks.planner_time_to_print_start_s = None if v is None else _safe_float(v, 0.0)
        if "time_to_print_stop_s" in pp:
            v = pp.get("time_to_print_stop_s")
            ks.planner_time_to_print_stop_s = None if v is None else _safe_float(v, 0.0)
        if "control_velocity_mms" in pp:
            ks.planner_control_velocity_mms = max(
                0.0, _safe_float(pp.get("control_velocity_mms"), 0.0)
            )

        ks.planner_last_update_t = now


def planner_is_fresh(cfg: Cfg, ks: KlipperState, now: float) -> bool:
    if ks.planner_last_update_t <= 0.0:
        return False
    return (now - ks.planner_last_update_t) <= max(0.1, float(cfg.planner_stale_timeout_s))


def select_control_velocity(cfg: Cfg, ks: KlipperState) -> float:
    return max(0.0, float(ks.planner_control_velocity_mms))


def planner_semantic_should_run(cfg: Cfg, ks: KlipperState, pump_running_hint: bool) -> tuple[bool, str]:
    if not ks.planner_print_window_active:
        return False, "idle"

    t_start = ks.planner_time_to_print_start_s
    t_stop = ks.planner_time_to_print_stop_s
    active_print_window = t_stop is not None

    # Active window semantics are planner-authoritative and must not depend
    # on backend "running" reporting, which can lag or be unavailable.
    if active_print_window:
        if t_stop <= max(0.0, float(cfg.pump_stop_lookahead_s)):
            # Keep command asserted during prestop and let target ramp logic
            # taper output; dropping command here causes premature hard-off.
            return True, "prestop"
        return True, "print"

    # No active print window: rely on horizon timing for prestart.
    if t_start is not None and t_start <= max(0.0, float(cfg.pump_start_lookahead_s)):
        return True, "prestart"

    # Between windows: optionally keep spinning only if already running and
    # the next window is very close.
    if (
        pump_running_hint
        and t_start is not None
        and t_start <= max(0.0, float(cfg.pump_run_lookahead_s))
    ):
        return True, "run_hold_gap"

    return False, "waiting_for_prestart"


def mode_allows_auto(control_mode: str) -> tuple[bool, str]:
    mode = str(control_mode or "UNKNOWN")
    if mode == "AUTO":
        return True, "auto"
    if mode == "MANUAL":
        return False, "manual"
    return False, "unknown"


def prestop_ramp_pct(cfg: Cfg, ks: KlipperState, nominal_target_pct: float) -> float:
    t_stop = ks.planner_time_to_print_stop_s
    if t_stop is None:
        return max(0.0, float(nominal_target_pct))

    ramp_s = max(0.0, float(cfg.pump_prestop_ramp_s))
    if ramp_s <= 0.0:
        return 0.0

    x = max(0.0, min(1.0, float(t_stop) / ramp_s))
    return max(0.0, float(nominal_target_pct)) * x


async def wait_moonraker_ready(log, ws_url: str, timeout_s: float = 30.0):
    deadline = time.monotonic() + timeout_s
    last_err = None
    while time.monotonic() < deadline:
        try:
            ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=20)
            await ws.close()
            return
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.5)
    raise RuntimeError(f"Moonraker not ready: {last_err}")


class MoonrakerClient:
    def __init__(self, ws_url: str, cfg: Cfg):
        self.ws_url = ws_url
        self.cfg = cfg
        self._ws = None
        self._id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._notify_q: asyncio.Queue = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._reader_task = None
        self._closed = False

    async def connect(self):
        self._ws = await websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20)
        self._reader_task = asyncio.create_task(self._reader_loop())

        try:
            await self.call("server.connection.identify", {
                "client_name": self.cfg.client_name,
                "version": self.cfg.client_version,
                "type": self.cfg.client_type,
                "url": self.cfg.client_url,
            })
        except Exception as e:
            msg = str(e)
            if "Method not found" in msg or "-32601" in msg:
                logging.getLogger("drukmix").warning(
                    "moonraker: server.connection.identify unavailable, continue without identify"
                )
            else:
                raise

        for m in (
            "drukmix_ping",
            "drukmix_status",
            "drukmix_stop",
            "drukmix_flush",
            "drukmix_set_gain",
            "drukmix_set_max_flow",
            "drukmix_set_min_print",
            "drukmix_set_min_flow",
            "drukmix_set_retract_gain",
            "drukmix_reset_fault",
            "drukmix_reload_cfg",
        ):
            try:
                await self.call("connection.register_remote_method", {"method_name": m})
            except Exception as e:
                msg = str(e)
                if "Method not found" in msg or "-32601" in msg:
                    logging.getLogger("drukmix").warning(
                        "moonraker: connection.register_remote_method unavailable, skip remote registration starting at method=%s",
                        m,
                    )
                    break
                raise

        await self.call("printer.objects.subscribe", {
            "objects": {
                "gcode_move": ["extrude_factor"],
                "drukmix_planner_probe": PLANNER_FIELD_NAMES,
            }
        })

    async def close(self):
        self._closed = True
        try:
            if self._ws:
                await self._ws.close()
        finally:
            self._ws = None
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except Exception:
                pass
            self._reader_task = None

    async def _reader_loop(self):
        try:
            while True:
                raw = await self._ws.recv()
                msg = json.loads(raw)
                if "id" in msg:
                    req_id = msg["id"]
                    fut = self._pending.pop(req_id, None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(RuntimeError(f"Moonraker RPC error: {msg['error']}"))
                        else:
                            fut.set_result(msg.get("result"))
                else:
                    await self._notify_q.put(msg)
        except Exception as e:
            for fut in self._pending.values():
                if fut and not fut.done():
                    fut.set_exception(e)
            self._pending.clear()
            if not self._closed:
                raise

    async def call(self, method: str, params: Optional[dict] = None):
        req_id = self._id
        self._id += 1
        req = {"jsonrpc": "2.0", "method": method, "id": req_id}
        if params is not None:
            req["params"] = params
        fut = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        async with self._send_lock:
            await self._ws.send(json.dumps(req))
        return await fut

    def notify_nowait(self):
        try:
            return self._notify_q.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def respond(self, level: str, msg: str):
        if level not in ("echo", "command", "error"):
            level = "echo"
        safe = msg.replace('"', "'")
        script = f'RESPOND TYPE={level} MSG="{safe}"'
        await self.call("printer.gcode.script", {"script": script})

    async def pause_print(self):
        await self.call("printer.print.pause", {})


def parse_remote_call(msg):
    method = msg.get("method")
    params = msg.get("params")

    if method == "notify_remote_method":
        if isinstance(params, list) and len(params) >= 1:
            rmethod = params[0]
            rparams = params[1] if len(params) >= 2 and isinstance(params[1], dict) else {}
            return rmethod, rparams
        return None

    if isinstance(method, str) and method.startswith("drukmix_"):
        if not isinstance(params, dict):
            params = {}
        return method, params

    return None


async def maybe_respond(mr, ui_notify: bool, level: str, msg: str):
    if not ui_notify:
        return
    try:
        await mr.respond(level, msg)
    except Exception:
        pass


def build_status_text(st, cfg: Cfg, ks: KlipperState, control_velocity: float) -> str:
    return (
        f"DrukMix: backend={st.backend} link_ok={int(st.link_ok)} "
        f"mode={st.control_mode} running={-1 if st.running is None else int(bool(st.running))} "
        f"rev={-1 if st.rev_active is None else int(bool(st.rev_active))} "
        f"fault={int(st.faulted)} code={st.fault_code} "
        f"fault_text={st.fault_text} "
        f"target_pct={st.target_pct} age_ms={st.age_ms} "
        f"queue_tail_s={ks.planner_queue_tail_s:.3f} ctrl_vel={control_velocity:.3f} "
        f"start_lookahead_s={cfg.pump_start_lookahead_s} stop_lookahead_s={cfg.pump_stop_lookahead_s} "
        f"max_flow_lpm={cfg.max_flow_lpm} gain_pct={cfg.gain_pct} "
        f"min_print_mms={cfg.min_print_mms} min_flow_pct={cfg.min_flow_pct} hold_s={cfg.min_flow_hold_s}"
    )


async def run_agent(cfg_path: str):
    cfg = load_config(cfg_path)
    if not cfg.enabled:
        return

    log = setup_logger(cfg.log_file, cfg.log_level)

    lock_path = os.path.expanduser("~/printer_data/logs/drukmix.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("drukmix: another instance is running")
        return

    filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
    liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)
    log.info(
        "drukmix: start filament_d=%s liters/mm=%.6f gain_pct=%s start_lookahead_s=%s stop_lookahead_s=%s",
        filament_d,
        liters_per_mm,
        cfg.gain_pct,
        cfg.pump_start_lookahead_s,
        cfg.pump_stop_lookahead_s,
    )

    mr = None
    backoff = 0.5

    while True:
        transport = None
        backend = None
        try:
            cfg = load_config(cfg_path)

            transport = BridgeUsbTransport(cfg.serial_port, cfg.serial_baud)
            if cfg.backend == "pumptpl":
                backend = PumpTplBackend(transport)
            else:
                backend = PumpVfdBackend(transport)

            if hasattr(backend, "debug_log"):
                backend.debug_log = bool(cfg.backend_debug_log)
                log.info("drukmix: backend_debug_log=%s backend=%s", int(bool(cfg.backend_debug_log)), cfg.backend)

            backend.open()

            core = DrukMixCore(CoreSettings(
                max_flow_lpm=cfg.max_flow_lpm,
                gain_pct=cfg.gain_pct,
                min_print_mms=cfg.min_print_mms,
                min_flow_pct=cfg.min_flow_pct,
                min_flow_hold_s=cfg.min_flow_hold_s,
                retract_deadband_mms=cfg.retract_deadband_mms,
                retract_gain_pct=cfg.retract_gain_pct,
            ))

            ks = KlipperState()
            fs = FlushState()

            await wait_moonraker_ready(log, cfg.moonraker_ws, timeout_s=30.0)
            mr = MoonrakerClient(cfg.moonraker_ws, cfg)
            await mr.connect()

            try:
                sub = await mr.call("printer.objects.query", {
                    "objects": {
                        "gcode_move": ["extrude_factor"],
                        "drukmix_planner_probe": PLANNER_FIELD_NAMES,
                    }
                })
                if isinstance(sub, dict):
                    status = sub.get("status", {})
                    if isinstance(status, dict):
                        apply_status(ks, status, time.monotonic())
            except Exception as e:
                log.warning(f"drukmix: initial status query failed: {e}")

            log.info("drukmix: running")

            last_log_t = 0.0
            last_cfg_check_t = 0.0
            last_cfg_mtime = 0.0
            last_fault_notify_key = None
            suppress_fault_until = 0.0
            pump_offline_since = None
            pause_latched_offline = False
            pause_latched_blocked_mode = False
            pause_latched_fault = False
            last_target_pct = 0.0
            last_probe_poll_t = 0.0
            last_transition_key = None

            while True:
                now = time.monotonic()

                if now - last_probe_poll_t >= 0.25:
                    last_probe_poll_t = now
                    try:
                        sub = await mr.call("printer.objects.query", {
                            "objects": {
                                "gcode_move": ["extrude_factor"],
                                "drukmix_planner_probe": PLANNER_FIELD_NAMES,
                            }
                        })
                        if isinstance(sub, dict):
                            status = sub.get("status", {})
                            if isinstance(status, dict):
                                apply_status(ks, status, now)
                    except Exception as e:
                        log.warning(f"drukmix: planner poll failed: {e}")

                if fs.active and fs.until_t > 0.0 and now >= fs.until_t:
                    fs.active = False
                    fs.pct = 0.0
                    fs.until_t = 0.0
                    backend.stop()

                if now - last_cfg_check_t >= max(0.2, cfg.cfg_reload_s):
                    last_cfg_check_t = now

                    try:
                        mtime = os.path.getmtime(cfg.cfg_path)
                    except Exception:
                        mtime = 0.0
                    if last_cfg_mtime == 0.0:
                        last_cfg_mtime = mtime
                    elif mtime != last_cfg_mtime:
                        last_cfg_mtime = mtime
                        cfg = load_config(cfg.cfg_path)
                        core = DrukMixCore(CoreSettings(
                            max_flow_lpm=cfg.max_flow_lpm,
                            gain_pct=cfg.gain_pct,
                            min_print_mms=cfg.min_print_mms,
                            min_flow_pct=cfg.min_flow_pct,
                            min_flow_hold_s=cfg.min_flow_hold_s,
                            retract_deadband_mms=cfg.retract_deadband_mms,
                            retract_gain_pct=cfg.retract_gain_pct,
                        ))
                        filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
                        liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)
                        await maybe_respond(mr, cfg.ui_notify, "command", "DrukMix: cfg reloaded")

                for _ in range(200):
                    msg = mr.notify_nowait()
                    if not msg:
                        break

                    if msg.get("method") == "notify_status_update":
                        params = msg.get("params", [])
                        if params and isinstance(params[0], dict):
                            st0 = params[0]
                            apply_status(ks, st0, now)
                            if cfg.planner_debug_log and "drukmix_planner_probe" in st0:
                                pp = st0["drukmix_planner_probe"]
                                logging.info(
                                    "drukmix agent probe update: queue_tail_s=%s t_start=%s t_stop=%s control_velocity=%s",
                                    pp.get("queue_tail_s"),
                                    pp.get("time_to_print_start_s"),
                                    pp.get("time_to_print_stop_s"),
                                    pp.get("control_velocity_mms"),
                                )
                        continue

                    rc = parse_remote_call(msg)
                    if not rc:
                        continue

                    method, params = rc

                    st_for_status = backend.poll_status()
                    control_velocity_for_status = select_control_velocity(cfg, ks)

                    if method == "drukmix_ping":
                        await maybe_respond(mr, cfg.ui_notify, "command", "DrukMix: ping OK")
                        continue

                    if method == "drukmix_status":
                        await maybe_respond(
                            mr,
                            cfg.ui_notify,
                            "command",
                            build_status_text(st_for_status, cfg, ks, control_velocity_for_status),
                        )
                        continue

                    if method == "drukmix_stop":
                        fs.active = False
                        fs.pct = 0.0
                        fs.until_t = 0.0
                        backend.stop()
                        last_target_pct = 0.0
                        try:
                            await mr.pause_print()
                        except Exception:
                            pass
                        await maybe_respond(mr, cfg.ui_notify, "error", "DrukMix: STOP")
                        continue

                    if method == "drukmix_flush":
                        pct = clamp(float(params.get("pct", 100.0)), 0.0, 100.0)
                        dur = max(0.0, float(params.get("duration", 0.0)))
                        fs.active = True
                        fs.pct = pct
                        fs.until_t = (now + dur) if dur > 0 else 0.0
                        backend.set_auto_target_pct(pct, rev=False)
                        last_target_pct = pct
                        await maybe_respond(mr, cfg.ui_notify, "command", f"DrukMix: FLUSH {pct:.1f}%")
                        continue

                    if method == "drukmix_set_gain":
                        cfg.gain_pct = clamp(float(params.get("pct", 100.0)), 0.0, 500.0)
                        core.cfg.gain_pct = cfg.gain_pct
                        await maybe_respond(mr, cfg.ui_notify, "command", f"DrukMix: gain_pct={cfg.gain_pct}")
                        continue

                    if method == "drukmix_set_max_flow":
                        cfg.max_flow_lpm = max(0.1, float(params.get("lpm", cfg.max_flow_lpm)))
                        core.cfg.max_flow_lpm = cfg.max_flow_lpm
                        await maybe_respond(mr, cfg.ui_notify, "command", f"DrukMix: max_flow_lpm={cfg.max_flow_lpm}")
                        continue

                    if method == "drukmix_set_min_print":
                        cfg.min_print_mms = max(0.0, float(params.get("mms", 0.0)))
                        core.cfg.min_print_mms = cfg.min_print_mms
                        await maybe_respond(mr, cfg.ui_notify, "command", f"DrukMix: min_print_mms={cfg.min_print_mms}")
                        continue

                    if method == "drukmix_set_min_flow":
                        cfg.min_flow_pct = clamp(float(params.get("pct", 0.0)), 0.0, 100.0)
                        cfg.min_flow_hold_s = max(0.0, float(params.get("hold", 0.0)))
                        core.cfg.min_flow_pct = cfg.min_flow_pct
                        core.cfg.min_flow_hold_s = cfg.min_flow_hold_s
                        await maybe_respond(mr, cfg.ui_notify, "command", f"DrukMix: min_flow_pct={cfg.min_flow_pct} hold_s={cfg.min_flow_hold_s}")
                        continue

                    if method == "drukmix_set_retract_gain":
                        cfg.retract_gain_pct = clamp(float(params.get("pct", 100.0)), 0.0, 500.0)
                        core.cfg.retract_gain_pct = cfg.retract_gain_pct
                        await maybe_respond(mr, cfg.ui_notify, "command", f"DrukMix: retract_gain_pct={cfg.retract_gain_pct}")
                        continue

                    if method == "drukmix_reset_fault":
                        backend.reset_fault()
                        suppress_fault_until = time.monotonic() + 3.0
                        last_fault_notify_key = None
                        await maybe_respond(mr, cfg.ui_notify, "command", "DrukMix: reset_fault sent")
                        continue

                    if method == "drukmix_reload_cfg":
                        last_cfg_mtime = 0.0
                        await maybe_respond(mr, cfg.ui_notify, "command", "DrukMix: reload requested")
                        continue

                st = backend.poll_status()
                planner_valid = planner_is_fresh(cfg, ks, now)
                force_stop_due_to_fault = False

                if hasattr(backend, "maybe_auto_reset_startup_fault"):
                    try:
                        did_reset = backend.maybe_auto_reset_startup_fault(
                            printing=planner_valid and ks.planner_print_window_active,
                            running=st.running,
                        )
                        if did_reset:
                            suppress_fault_until = time.monotonic() + 3.0
                            last_fault_notify_key = None
                            log.info("drukmix: safe one-shot auto-reset for Err16")
                    except Exception as e:
                        log.warning(f"drukmix: err16 auto-reset check failed: {e}")

                if st.faulted and st.fault_code > 0 and time.monotonic() >= suppress_fault_until:
                    force_stop_due_to_fault = True
                    if planner_valid and ks.planner_print_window_active:
                        backend.stop()
                        last_target_pct = 0.0
                        if st.pause_print and (not pause_latched_fault):
                            log.warning(
                                "DBG pause reason=fault fault=%d code=%d link_ok=%d mode=%s planner_valid=%d tail_s=%.3f",
                                int(st.faulted),
                                st.fault_code,
                                int(st.link_ok),
                                st.control_mode,
                                int(planner_valid),
                                ks.planner_queue_tail_s,
                            )
                            try:
                                await mr.pause_print()
                            except Exception:
                                pass
                            pause_latched_fault = True

                    fault_key = (st.backend, st.fault_code, bool(st.link_ok))
                    if fault_key != last_fault_notify_key:
                        msg = st.fault_text or f"VFD fault {st.fault_code}"
                        if st.possible_causes:
                            msg += " | Causes: " + " ; ".join(st.possible_causes[:2])
                        if st.solutions:
                            msg += " | Fix: " + " ; ".join(st.solutions[:2])
                        await maybe_respond(mr, cfg.ui_notify, "error", msg)
                        last_fault_notify_key = fault_key
                else:
                    last_fault_notify_key = None
                    pause_latched_fault = False

                control_velocity = select_control_velocity(cfg, ks)

                semantic_should_run_now = False
                semantic_reason = "idle"
                if planner_valid:
                    semantic_should_run_now, semantic_reason = planner_semantic_should_run(
                        cfg,
                        ks,
                        bool(st.running),
                    )

                auto_allowed, mode_reason = mode_allows_auto(st.control_mode)
                should_run_now = semantic_should_run_now and auto_allowed

                transition_key = (
                    int(planner_valid),
                    int(ks.planner_print_window_active),
                    semantic_reason,
                    mode_reason,
                    -1 if st.running is None else int(bool(st.running)),
                    int(should_run_now),
                    None if ks.planner_time_to_print_start_s is None else round(float(ks.planner_time_to_print_start_s), 3),
                    None if ks.planner_time_to_print_stop_s is None else round(float(ks.planner_time_to_print_stop_s), 3),
                )
                if transition_key != last_transition_key:
                    log.info(
                        "drukmix transition: planner_valid=%d print_window=%d running=%s ctrl_vel=%.3f tail_s=%.3f t_start=%s t_stop=%s should_run=%d semantic=%s mode=%s last_target_pct=%.2f",
                        int(planner_valid),
                        int(ks.planner_print_window_active),
                        st.running,
                        control_velocity,
                        ks.planner_queue_tail_s,
                        ks.planner_time_to_print_start_s,
                        ks.planner_time_to_print_stop_s,
                        int(should_run_now),
                        semantic_reason,
                        mode_reason,
                        last_target_pct,
                    )
                    last_transition_key = transition_key

                if force_stop_due_to_fault:
                    target_pct = 0.0
                    rev = False
                    stop = True
                elif fs.active:
                    target_pct = fs.pct
                    rev = False
                    stop = False
                elif not planner_valid:
                    target_pct = 0.0
                    rev = False
                    stop = True
                elif not auto_allowed:
                    target_pct = 0.0
                    rev = False
                    stop = True
                elif not should_run_now:
                    target_pct = 0.0
                    rev = False
                    stop = True
                else:
                    out = core.compute(CoreInput(
                        printing=ks.planner_print_window_active,
                        paused=False,
                        live_extruder_velocity=control_velocity,
                        extrude_factor=ks.extrude_factor,
                        liters_per_mm=liters_per_mm,
                    ), now)
                    target_pct = out.target_pct
                    rev = out.rev
                    stop = out.stop

                    if semantic_reason == "prestart":
                        target_pct = max(0.0, float(cfg.pump_prestart_pct))
                        rev = False
                        stop = target_pct <= 0.0
                    elif semantic_reason == "prestop":
                        target_pct = prestop_ramp_pct(cfg, ks, out.target_pct)
                        rev = False
                        stop = target_pct <= 0.0

                if stop:
                    backend.stop()
                    last_target_pct = 0.0
                else:
                    backend.set_auto_target_pct(target_pct, rev)
                    last_target_pct = target_pct

                if st.link_ok or (not should_run_now):
                    pump_offline_since = None
                else:
                    if pump_offline_since is None:
                        pump_offline_since = now

                offline_by_age = False
                if st.age_ms is not None:
                    offline_by_age = st.age_ms >= int(max(0.0, cfg.pump_offline_timeout_s) * 1000.0)

                offline_by_time = False
                if pump_offline_since is not None:
                    offline_by_time = (now - pump_offline_since) >= max(0.0, cfg.pump_offline_timeout_s)

                offline_pause_condition = (
                    cfg.pause_on_pump_offline
                    and should_run_now
                    and (not st.link_ok)
                    and (offline_by_age or offline_by_time)
                )

                if offline_pause_condition and (not pause_latched_offline):
                    log.warning(
                        "DBG pause reason=pump_offline planner_valid=%d tail_s=%.3f link_ok=%d age_ms=%s mode=%s ctrl_vel=%.3f target_pct=%.2f should_run=%d off_age=%d off_time=%d t_start=%s t_stop=%s cmd_reason=%s",
                        int(planner_valid),
                        ks.planner_queue_tail_s,
                        int(st.link_ok),
                        st.age_ms,
                        st.control_mode,
                        control_velocity,
                        target_pct,
                        int(should_run_now),
                        int(offline_by_age),
                        int(offline_by_time),
                        ks.planner_time_to_print_start_s,
                        ks.planner_time_to_print_stop_s,
                        semantic_reason,
                    )
                    try:
                        await mr.pause_print()
                    except Exception:
                        pass
                    await maybe_respond(mr, cfg.ui_notify, "error", "DrukMix: pump offline")
                    pause_latched_offline = True
                elif not offline_pause_condition:
                    pause_latched_offline = False

                blocked_mode_pause_condition = cfg.pause_on_manual_mode and semantic_should_run_now and not auto_allowed

                if blocked_mode_pause_condition and (not pause_latched_blocked_mode):
                    log.warning(
                        "DBG pause reason=blocked_mode planner_valid=%d tail_s=%.3f mode=%s link_ok=%d ctrl_vel=%.3f target_pct=%.2f mode_reason=%s",
                        int(planner_valid),
                        ks.planner_queue_tail_s,
                        st.control_mode,
                        int(st.link_ok),
                        control_velocity,
                        target_pct,
                        mode_reason,
                    )
                    try:
                        await mr.pause_print()
                    except Exception:
                        pass
                    await maybe_respond(mr, cfg.ui_notify, "error", f"DrukMix: blocked mode {st.control_mode}")
                    pause_latched_blocked_mode = True
                elif not blocked_mode_pause_condition:
                    pause_latched_blocked_mode = False

                if now - last_log_t >= max(0.2, cfg.log_period_s):
                    last_log_t = now
                    log.info(
                        "drukmix: backend=%s mode=%s running=%s planner_valid=%d tail_s=%.3f ctrl_vel=%.3f ef=%.3f target_pct=%.2f rev=%d link_ok=%d fault=%d code=%d age_ms=%s target_mlpm=%d hw_raw=%d pump_flags=%d ack_seq=%d applied=%d start_lookahead_s=%.3f run_lookahead_s=%.3f stop_lookahead_s=%.3f stale_timeout_s=%.3f print_window=%d t_start=%s t_stop=%s pump_cmd=%d cmd_reason=%s mode_reason=%s",
                        st.backend,
                        st.control_mode,
                        st.running,
                        int(planner_valid),
                        ks.planner_queue_tail_s,
                        control_velocity,
                        ks.extrude_factor,
                        target_pct,
                        int(rev),
                        int(st.link_ok),
                        int(st.faulted),
                        st.fault_code,
                        st.age_ms,
                        int(getattr(st, "target_milli_lpm", -1)),
                        int(getattr(st, "hw_setpoint_raw", -1)),
                        int(getattr(st, "pump_flags", -1)),
                        int(getattr(st, "last_ack_seq", -1)),
                        int(getattr(st, "applied_code", -1)),
                        cfg.pump_start_lookahead_s,
                        cfg.pump_run_lookahead_s,
                        cfg.pump_stop_lookahead_s,
                        cfg.planner_stale_timeout_s,
                        int(ks.planner_print_window_active),
                        ks.planner_time_to_print_start_s,
                        ks.planner_time_to_print_stop_s,
                        int(should_run_now),
                        semantic_reason,
                        mode_reason,
                    )

                await asyncio.sleep(1.0 / max(cfg.update_hz, 0.5))

        except Exception as e:
            log.error(f"drukmix: error: {e}")
            try:
                if backend:
                    backend.stop()
            except Exception:
                pass
            try:
                if backend:
                    backend.close()
            except Exception:
                pass
            try:
                if mr:
                    await mr.close()
            except Exception:
                pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, 10.0)


def main():
    cfg_path = os.environ.get("DRUKMIX_CONFIG", os.path.expanduser("~/printer_data/config/drukmix.cfg"))
    asyncio.run(run_agent(cfg_path))


if __name__ == "__main__":
    main()
