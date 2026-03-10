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

    update_hz: float
    log_period_s: float

    pause_on_pump_offline: bool
    pause_on_manual_mode: bool
    ui_notify: bool

    bridge_offline_timeout_s: float
    pump_offline_timeout_s: float

    log_file: str
    log_level: str

    flush_confirm: bool
    cfg_reload_s: float
    cfg_path: str = ""


@dataclasses.dataclass
class KlipperState:
    print_state: str = "unknown"
    idle_state: str = "unknown"
    is_paused: bool = False
    klippy_state: str = "unknown"
    extrude_factor: float = 1.0
    live_extruder_velocity: float = 0.0


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

        update_hz=_get_float(s, "update_hz", 6.0),
        log_period_s=_get_float(s, "log_period_s", 5.0),

        pause_on_pump_offline=get_bool("pause_on_pump_offline", True),
        pause_on_manual_mode=get_bool("pause_on_manual_mode", True),
        ui_notify=get_bool("ui_notify", True),

        bridge_offline_timeout_s=_get_float(s, "bridge_offline_timeout_s", 1.0),
        pump_offline_timeout_s=_get_float(s, "pump_offline_timeout_s", 1.2),

        log_file=_get_str(s, "log_file", os.path.expanduser("~/printer_data/logs/drukmix.log")),
        log_level=_get_str(s, "log_level", "info").lower(),

        flush_confirm=get_bool("flush_confirm", False),
        cfg_reload_s=_get_float(s, "cfg_reload_s", 2.0),
        cfg_path=path,
    )


def setup_logger(log_file: str) -> logging.Logger:
    lg = logging.getLogger("drukmix")
    lg.setLevel(logging.INFO)
    lg.handlers.clear()

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    lg.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
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


def apply_status(ks: KlipperState, st: Dict[str, Any]) -> None:
    if "print_stats" in st and "state" in st["print_stats"]:
        ks.print_state = str(st["print_stats"]["state"])
    if "idle_timeout" in st and "state" in st["idle_timeout"]:
        ks.idle_state = str(st["idle_timeout"]["state"])
    if "pause_resume" in st and "is_paused" in st["pause_resume"]:
        ks.is_paused = bool(st["pause_resume"]["is_paused"])
    if "webhooks" in st and "state" in st["webhooks"]:
        ks.klippy_state = str(st["webhooks"]["state"])
    if "gcode_move" in st and "extrude_factor" in st["gcode_move"]:
        try:
            ks.extrude_factor = float(st["gcode_move"]["extrude_factor"])
        except Exception:
            ks.extrude_factor = 1.0
    if "motion_report" in st and "live_extruder_velocity" in st["motion_report"]:
        try:
            ks.live_extruder_velocity = float(st["motion_report"]["live_extruder_velocity"])
        except Exception:
            ks.live_extruder_velocity = 0.0


def is_printing(ks: KlipperState) -> bool:
    ps = ks.print_state.lower().strip()
    if ps:
        return ps == "printing"
    it = ks.idle_state.lower().strip()
    return it == "printing"


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
                "print_stats": ["state"],
                "idle_timeout": ["state"],
                "pause_resume": ["is_paused"],
                "gcode_move": ["extrude_factor"],
                "motion_report": ["live_extruder_velocity"],
                "webhooks": ["state", "state_message"],
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


def build_status_text(st, cfg: Cfg) -> str:
    return (
        f"DrukMix: backend={st.backend} link_ok={int(st.link_ok)} "
        f"mode={st.control_mode} running={-1 if st.running is None else int(bool(st.running))} "
        f"rev={-1 if st.rev_active is None else int(bool(st.rev_active))} "
        f"fault={int(st.faulted)} code={st.fault_code} "
        f"fault_text={st.fault_text} "
        f"target_pct={st.target_pct} age_ms={st.age_ms} "
        f"max_flow_lpm={cfg.max_flow_lpm} gain_pct={cfg.gain_pct} "
        f"min_print_mms={cfg.min_print_mms} min_flow_pct={cfg.min_flow_pct} hold_s={cfg.min_flow_hold_s}"
    )


async def run_agent(cfg_path: str):
    cfg = load_config(cfg_path)
    if not cfg.enabled:
        return

    log = setup_logger(cfg.log_file)

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
    log.info(f"drukmix: start filament_d={filament_d} liters/mm={liters_per_mm:.6f} gain_pct={cfg.gain_pct}")

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
                        "print_stats": ["state"],
                        "idle_timeout": ["state"],
                        "pause_resume": ["is_paused"],
                        "gcode_move": ["extrude_factor"],
                        "motion_report": ["live_extruder_velocity"],
                        "webhooks": ["state", "state_message"],
                    }
                })
                if isinstance(sub, dict):
                    status = sub.get("status", {})
                    if isinstance(status, dict):
                        apply_status(ks, status)
            except Exception as e:
                log.warning(f"drukmix: initial status query failed: {e}")

            log.info("drukmix: running")

            last_log_t = 0.0
            last_cfg_check_t = 0.0
            last_cfg_mtime = 0.0
            last_fault_notify_key = None
            suppress_fault_until = 0.0

            while True:
                now = time.monotonic()

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
                            apply_status(ks, st0)

                            if (
                                (not fs.active)
                                and ("motion_report" in st0)
                                and ("live_extruder_velocity" in st0["motion_report"])
                            ):
                                printing_now = is_printing(ks)
                                if printing_now and (not ks.is_paused):
                                    out = core.compute(CoreInput(
                                        printing=printing_now,
                                        paused=ks.is_paused,
                                        live_extruder_velocity=ks.live_extruder_velocity,
                                        extrude_factor=ks.extrude_factor,
                                        liters_per_mm=liters_per_mm,
                                    ), now)
                                    backend.set_auto_target_pct(out.target_pct, out.rev)
                        continue

                    rc = parse_remote_call(msg)
                    if not rc:
                        continue

                    method, params = rc

                    if method == "drukmix_ping":
                        await maybe_respond(mr, cfg.ui_notify, "command", "DrukMix: ping OK")
                        continue

                    if method == "drukmix_status":
                        st = backend.poll_status()
                        await maybe_respond(mr, cfg.ui_notify, "command", build_status_text(st, cfg))
                        continue

                    if method == "drukmix_stop":
                        fs.active = False
                        fs.pct = 0.0
                        fs.until_t = 0.0
                        backend.stop()
                        if is_printing(ks) and not ks.is_paused:
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

                printing = is_printing(ks)

                if hasattr(backend, "maybe_auto_reset_startup_fault"):
                    try:
                        did_reset = backend.maybe_auto_reset_startup_fault(printing=printing, running=st.running)
                        if did_reset:
                            suppress_fault_until = time.monotonic() + 3.0
                            last_fault_notify_key = None
                            log.info("drukmix: safe one-shot auto-reset for Err16")
                    except Exception as e:
                        log.warning(f"drukmix: err16 auto-reset check failed: {e}")

                if st.faulted and st.fault_code > 0 and time.monotonic() >= suppress_fault_until:
                    if printing:
                        backend.stop()
                        if st.pause_print and not ks.is_paused:
                            log.warning(
                                "DBG pause reason=fault print=%s idle=%s paused=%d fault=%d code=%d link_ok=%d mode=%s",
                                ks.print_state,
                                ks.idle_state,
                                int(ks.is_paused),
                                int(st.faulted),
                                st.fault_code,
                                int(st.link_ok),
                                st.control_mode,
                            )
                            try:
                                await mr.pause_print()
                            except Exception:
                                pass

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

                if fs.active:
                    target_pct = fs.pct
                    rev = False
                    stop = False
                else:
                    out = core.compute(CoreInput(
                        printing=printing,
                        paused=ks.is_paused,
                        live_extruder_velocity=ks.live_extruder_velocity,
                        extrude_factor=ks.extrude_factor,
                        liters_per_mm=liters_per_mm,
                    ), now)
                    target_pct = out.target_pct
                    rev = out.rev
                    stop = out.stop

                if stop:
                    backend.stop()
                else:
                    backend.set_auto_target_pct(target_pct, rev)

                if cfg.pause_on_pump_offline and printing and (not ks.is_paused) and (not st.link_ok):
                    log.warning(
                        "DBG pause reason=pump_offline print=%s idle=%s paused=%d link_ok=%d age_ms=%s mode=%s vel=%.3f target_pct=%.2f",
                        ks.print_state,
                        ks.idle_state,
                        int(ks.is_paused),
                        int(st.link_ok),
                        st.age_ms,
                        st.control_mode,
                        ks.live_extruder_velocity,
                        target_pct,
                    )
                    try:
                        await mr.pause_print()
                    except Exception:
                        pass
                    await maybe_respond(mr, cfg.ui_notify, "error", "DrukMix: pump offline")

                if cfg.pause_on_manual_mode and printing and (not ks.is_paused) and st.control_mode != "AUTO":
                    log.warning(
                        "DBG pause reason=manual_mode print=%s idle=%s paused=%d mode=%s link_ok=%d vel=%.3f target_pct=%.2f",
                        ks.print_state,
                        ks.idle_state,
                        int(ks.is_paused),
                        st.control_mode,
                        int(st.link_ok),
                        ks.live_extruder_velocity,
                        target_pct,
                    )
                    try:
                        await mr.pause_print()
                    except Exception:
                        pass
                    await maybe_respond(mr, cfg.ui_notify, "error", f"DrukMix: manual mode {st.control_mode}")

                if now - last_log_t >= max(0.2, cfg.log_period_s):
                    last_log_t = now
                    log.info(
                        "drukmix: backend=%s mode=%s print=%s idle=%s paused=%d klippy=%s vel=%.3f ef=%.3f target_pct=%.2f rev=%d link_ok=%d fault=%d code=%d age_ms=%s",
                        st.backend,
                        st.control_mode,
                        ks.print_state,
                        ks.idle_state,
                        int(ks.is_paused),
                        ks.klippy_state,
                        ks.live_extruder_velocity,
                        ks.extrude_factor,
                        target_pct,
                        int(rev),
                        int(st.link_ok),
                        int(st.faulted),
                        st.fault_code,
                        st.age_ms,
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
