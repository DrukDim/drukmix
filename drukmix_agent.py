#!/usr/bin/env python3
import asyncio
import configparser
import dataclasses
import json
import math
import os
import re
import struct
import time
import logging
import fcntl
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Tuple

import serial
import websockets

# ---------------- USB protocol (must match bridge firmware) ----------------
PROTO = 1
USB_SET_FLOW = 1       # body: i32 milli_lpm, u8 flags
USB_SET_MAXLPM = 3     # body: i32 pump_max_milli_lpm
USB_BRIDGE_STATUS = 101

# Pump flags (passed through bridge)
FLAG_REV = 0x01
FLAG_STOP = 0x02
FLAG_AUTO = 0x04

# Pump err_flags bits (from pump firmware)
EF_MANUAL_FWD = 0x0010
EF_MANUAL_REV = 0x0020
EF_AUTO_ALLOWED = 0x0040
EF_AUTO_ACTIVE = 0x0080
EF_DIR_ASSERTED = 0x0100
EF_WIPER_TPL = 0x0200


# ----------------- low-level helpers -----------------
def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(payload: bytes) -> bytes:
    out = bytearray()
    code_ptr = 0
    out.append(0)
    code = 1
    for b in payload:
        if b == 0:
            out[code_ptr] = code
            code_ptr = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_ptr] = code
                code_ptr = len(out)
                out.append(0)
                code = 1
    out[code_ptr] = code
    return bytes(out)


def cobs_decode(frame: bytes) -> Optional[bytes]:
    out = bytearray()
    i, n = 0, len(frame)
    while i < n:
        code = frame[i]
        if code == 0:
            return None
        i += 1
        for _ in range(1, code):
            if i >= n:
                return None
            out.append(frame[i])
            i += 1
        if code != 0xFF and i < n:
            out.append(0)
    return bytes(out)


def build_usb_packet(msg_type: int, seq: int, body: bytes) -> bytes:
    mono_ms = int(time.monotonic() * 1000) & 0xFFFFFFFF
    hdr = struct.pack("<BBHI", PROTO, msg_type, seq & 0xFFFF, mono_ms)
    payload = hdr + body
    crc = crc16_ccitt_false(payload)
    payload += struct.pack("<H", crc)
    return cobs_encode(payload) + b"\x00"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ----------------- config -----------------
@dataclasses.dataclass
class Cfg:
    enabled: bool
    moonraker_ws: str
    serial_port: str
    serial_baud: int

    client_name: str
    client_version: str
    client_type: str
    client_url: str

    pump_max_lpm: float
    min_run_lpm: float
    min_run_hold_s: float
    flow_gain: float

    retract_deadband_mm_s: float
    retract_gain: float

    printer_cfg: str
    filament_diameter_fallback: float

    update_hz: float
    poll_hz: float

    # Safety policies
    pause_on_pump_offline: bool
    pause_on_manual_during_print: bool
    ui_notify: bool

    bridge_offline_timeout_s: float
    pump_offline_timeout_s: float

    # Logging
    log_file: str
    log_level: str
    log_period_s: float

    # FLUSH reliability
    flush_burst_count: int
    flush_burst_interval_ms: int
    flush_confirm: bool
    flush_confirm_timeout_s: float
    flush_confirm_tolerance_code: int
    flush_confirm_retries: int

    cfg_reload_s: float
    cfg_path: str = ""


def _strip_inline_comment(v: str) -> str:
    if v is None:
        return ""
    v = str(v)
    v = v.split("#", 1)[0]
    v = v.split(";", 1)[0]
    return v.strip()


def _get_float(s: configparser.SectionProxy, key: str, default: float) -> float:
    raw = s.get(key, str(default))
    return float(_strip_inline_comment(raw))


def _get_int(s: configparser.SectionProxy, key: str, default: int) -> int:
    raw = s.get(key, str(default))
    return int(float(_strip_inline_comment(raw)))


def _get_str(s: configparser.SectionProxy, key: str, default: str) -> str:
    raw = s.get(key, default)
    return _strip_inline_comment(raw)


def load_config(path: str) -> Cfg:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cp.read(path):
        raise FileNotFoundError(path)
    s = cp["drukmix"]

    def get_bool(k, d=False):
        raw = s.get(k, str(d))
        raw = _strip_inline_comment(raw).lower()
        return raw in ("1", "true", "yes", "on")

    return Cfg(
        enabled=get_bool("enabled", True),
        moonraker_ws=_get_str(s, "moonraker_ws", "ws://127.0.0.1:7125/websocket"),
        serial_port=_get_str(s, "serial_port", ""),
        serial_baud=_get_int(s, "serial_baud", 921600),

        client_name=_get_str(s, "client_name", "drukmix"),
        client_version=_get_str(s, "client_version", "2.2.0"),
        client_type=_get_str(s, "client_type", "agent"),
        client_url=_get_str(s, "client_url", "https://drukos.local/drukmix"),

        pump_max_lpm=_get_float(s, "pump_max_lpm", 10.0),
        min_run_lpm=_get_float(s, "min_run_lpm", 0.20),
        min_run_hold_s=_get_float(s, "min_run_hold_s", 5.0),
        flow_gain=_get_float(s, "flow_gain", 1.0),

        retract_deadband_mm_s=_get_float(s, "retract_deadband_mm_s", 0.20),
        retract_gain=_get_float(s, "retract_gain", 1.0),

        printer_cfg=_get_str(s, "printer_cfg", os.path.expanduser("~/printer_data/config/printer.cfg")),
        filament_diameter_fallback=_get_float(s, "filament_diameter_fallback", 35.0),

        update_hz=_get_float(s, "update_hz", 6.0),
        poll_hz=_get_float(s, "poll_hz", 0.5),

        pause_on_pump_offline=get_bool("pause_on_pump_offline", True),
        pause_on_manual_during_print=get_bool("pause_on_manual_during_print", True),
        ui_notify=get_bool("ui_notify", True),

        bridge_offline_timeout_s=_get_float(s, "bridge_offline_timeout_s", 1.0),
        pump_offline_timeout_s=_get_float(s, "pump_offline_timeout_s", 1.2),

        log_file=_get_str(s, "log_file", os.path.expanduser("~/printer_data/logs/drukmix.log")),
        log_level=_get_str(s, "log_level", "info").lower(),
        log_period_s=_get_float(s, "log_period_s", 5.0),

        flush_burst_count=_get_int(s, "flush_burst_count", 10),
        flush_burst_interval_ms=_get_int(s, "flush_burst_interval_ms", 20),
        flush_confirm=get_bool("flush_confirm", True),
        flush_confirm_timeout_s=_get_float(s, "flush_confirm_timeout_s", 1.2),
        flush_confirm_tolerance_code=_get_int(s, "flush_confirm_tolerance_code", 8),
        flush_confirm_retries=_get_int(s, "flush_confirm_retries", 2),

        cfg_reload_s=_get_float(s, "cfg_reload_s", 2.0),
        cfg_path=path,
    )


# ----------------- printer cfg reading -----------------
def read_filament_diameter_from_printer_cfg(path: str, fallback: float) -> float:
    try:
        txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return fallback
    m = re.search(r"(?ms)^\[extruder\]\s*(.*?)(^\[|\Z)", txt)
    section = m.group(1) if m else txt
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


# ----------------- runtime state -----------------
@dataclasses.dataclass
class KlipperState:
    print_state: str = "unknown"
    idle_state: str = "unknown"
    is_paused: bool = False
    klippy_state: str = "unknown"
    extrude_factor: float = 1.0
    live_extruder_velocity: float = 0.0


@dataclasses.dataclass
class LinkState:
    last_bridge_frame_t: float = 0.0
    pump_link: int = 0
    age_ms: Optional[int] = None
    last_code: int = 0
    err_flags: int = 0


@dataclasses.dataclass
class FlushState:
    active: bool = False
    lpm: float = 0.0
    until_t: float = 0.0


@dataclasses.dataclass
class Overrides:
    gain: Optional[float] = None
    log_level: Optional[str] = None


# ----------------- logging setup -----------------
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


# ----------------- Moonraker client -----------------
class MoonrakerClient:
    def __init__(self, ws_url: str, cfg: Cfg):
        self.ws_url = ws_url
        self.cfg = cfg
        self._ws = None
        self._id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._notify_q: asyncio.Queue = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._reader_task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect(self):
        self._ws = await websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20)
        self._reader_task = asyncio.create_task(self._reader_loop())

        await self.call("server.connection.identify", {
            "client_name": self.cfg.client_name,
            "version": self.cfg.client_version,
            "type": self.cfg.client_type,
            "url": self.cfg.client_url,
        })

        for m in (
            "drukmix_ping",
            "drukmix_status",
            "drukmix_flush",
            "drukmix_flush_stop",
            "drukmix_set_gain",
            "drukmix_set_debug",
            "drukmix_reload_cfg",
        ):
            await self.call("connection.register_remote_method", {"method_name": m})

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
            except asyncio.CancelledError:
                pass
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

    async def call(self, method: str, params: Optional[dict] = None) -> Any:
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

    def notify_nowait(self) -> Optional[dict]:
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


# ----------------- Bridge serial -----------------
def parse_bridge_status(payload: bytes) -> Optional[Dict[str, Any]]:
    if len(payload) < 10:
        return None
    got_crc = struct.unpack_from("<H", payload, len(payload) - 2)[0]
    calc_crc = crc16_ccitt_false(payload[:-2])
    if got_crc != calc_crc:
        return None

    proto, msg_type, seq, mono_ms = struct.unpack_from("<BBHI", payload, 0)
    if proto != PROTO or msg_type != USB_BRIDGE_STATUS:
        return None

    body = payload[8:-2]
    if len(body) < (1 + 2 + 2 + 1 + 2 + 2 + 2 + 4):
        return None

    pump_link = body[0]
    last_seen_div10 = struct.unpack_from("<H", body, 1)[0]
    applied_code = body[5]
    err_flags = struct.unpack_from("<H", body, 6)[0]
    age_ms = None if last_seen_div10 == 65535 else int(last_seen_div10) * 10

    return {
        "pump_link": int(pump_link),
        "age_ms": age_ms,
        "code": int(applied_code),
        "err_flags": int(err_flags),
    }


class BridgeSerial:
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.seq = 1
        self.rx_buf = bytearray()

    def open(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.0)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None

    def send_set_maxlpm(self, pump_max_lpm: float):
        milli = int(pump_max_lpm * 1000)
        pkt = build_usb_packet(USB_SET_MAXLPM, self.seq, struct.pack("<i", milli))
        self.seq = (self.seq + 1) & 0xFFFF
        self.ser.write(pkt)

    def send_flow(self, lpm: float, flags: int):
        milli = int(lpm * 1000)
        pkt = build_usb_packet(USB_SET_FLOW, self.seq, struct.pack("<iB", milli, flags & 0xFF))
        self.seq = (self.seq + 1) & 0xFFFF
        self.ser.write(pkt)

    def read_status_frames(self):
        data = self.ser.read(512)
        if data:
            self.rx_buf.extend(data)

        frames = []
        while True:
            try:
                idx = self.rx_buf.index(0)
            except ValueError:
                break
            frame = bytes(self.rx_buf[:idx])
            del self.rx_buf[:idx + 1]
            if not frame:
                continue
            dec = cobs_decode(frame)
            if dec is None:
                continue
            st = parse_bridge_status(dec)
            if st:
                frames.append(st)
        return frames


# ----------------- logic helpers -----------------
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
    ps = ks.print_state.lower()
    it = ks.idle_state.lower()
    return (ps == "printing") or (it == "printing")


def parse_remote_call(msg: dict) -> Optional[Tuple[str, dict]]:
    m = msg.get("method")
    if not isinstance(m, str) or not m.startswith("drukmix_"):
        return None
    p = msg.get("params") or {}
    return (m, p) if isinstance(p, dict) else (m, {})


def decode_mode(err_flags: int) -> str:
    if err_flags & EF_MANUAL_FWD:
        return "MANUAL_FWD"
    if err_flags & EF_MANUAL_REV:
        return "MANUAL_REV"
    return "AUTO"


# ----------------- agent main -----------------
async def run_agent(cfg_path: str):
    cfg = load_config(cfg_path)
    if not cfg.enabled:
        print("drukmix: disabled")
        return

    log = setup_logger(cfg.log_file)

    # single instance lock
    lock_path = os.path.expanduser("~/printer_data/logs/drukmix.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("drukmix: another instance is running (lock busy). Exiting.")
        return

    filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
    liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)

    ks = KlipperState()
    ls = LinkState()
    fs = FlushState()
    ov = Overrides()
    status_event = asyncio.Event()

    last_send_t = 0.0
    last_poll_t = 0.0
    last_cfg_check = 0.0
    last_cfg_mtime = 0.0

    # transition tracking for UI messages
    last_bridge_ok = None
    last_pump_ok = None
    last_mode = None  # MANUAL_FWD / MANUAL_REV / AUTO
    last_pause_reason = None
    last_state_msg_t = 0.0
    last_log_t = 0.0

    def eff_gain() -> float:
        return float(ov.gain) if ov.gain is not None else cfg.flow_gain

    def eff_log_level() -> str:
        lvl = (ov.log_level or cfg.log_level or "info").lower()
        return lvl if lvl in ("off", "info", "debug") else "info"

    def send_period() -> float:
        return 1.0 / max(cfg.update_hz, 0.5)

    def poll_period() -> float:
        return 1.0 / max(cfg.poll_hz, 0.1)

    async def maybe_respond(level: str, msg: str, min_interval_s: float = 0.4):
        nonlocal last_state_msg_t
        if not cfg.ui_notify:
            return
        now = time.monotonic()
        if now - last_state_msg_t < min_interval_s:
            return
        last_state_msg_t = now
        try:
            await mr.respond(level, msg)
        except Exception:
            pass

    async def pause_with_popup(reason: str):
        # prevent spamming pause calls
        nonlocal last_pause_reason
        if ks.is_paused:
            return
        if last_pause_reason == reason:
            return
        last_pause_reason = reason
        try:
            await mr.pause_print()
        except Exception:
            pass
        await maybe_respond("error", reason, min_interval_s=0.0)

    async def burst_send(lpm: float, flags: int):
        count = max(1, int(cfg.flush_burst_count))
        interval = max(0.0, float(cfg.flush_burst_interval_ms)) / 1000.0
        for _ in range(count):
            try:
                bridge.send_flow(lpm, flags)
            except Exception:
                pass
            if interval > 0:
                await asyncio.sleep(interval)

    async def confirm_applied(want_code: int, stop: bool) -> bool:
        tol = int(clamp(cfg.flush_confirm_tolerance_code, 0, 50))
        deadline = time.monotonic() + max(0.05, cfg.flush_confirm_timeout_s)
        while time.monotonic() < deadline:
            if stop:
                if ls.last_code == 0:
                    return True
            else:
                if abs(ls.last_code - want_code) <= tol:
                    return True
            status_event.clear()
            try:
                await asyncio.wait_for(status_event.wait(), timeout=0.10)
            except asyncio.TimeoutError:
                pass
        return False

    def expected_code(lpm: float, max_lpm: float) -> int:
        if max_lpm <= 0:
            return 0
        c = int(round((clamp(lpm, 0.0, max_lpm) / max_lpm) * 255.0))
        return int(clamp(c, 0, 255))

    log.info(f"drukmix: start filament_d={filament_d} liters/mm={liters_per_mm:.6f} gain={cfg.flow_gain}")

    backoff = 0.5
    while True:
        bridge = None
        mr = None
        serial_task = None
        try:
            bridge = BridgeSerial(cfg.serial_port, cfg.serial_baud)
            bridge.open()

            mr = MoonrakerClient(cfg.moonraker_ws, cfg)
            await mr.connect()
            backoff = 0.5

            bridge.send_set_maxlpm(cfg.pump_max_lpm)

            # initial snapshot
            try:
                res = await mr.call("printer.objects.query", {"objects": {
                    "print_stats": ["state"],
                    "idle_timeout": ["state"],
                    "pause_resume": ["is_paused"],
                    "gcode_move": ["extrude_factor"],
                    "motion_report": ["live_extruder_velocity"],
                    "webhooks": ["state", "state_message"],
                }})
                st = (res or {}).get("status") or {}
                if isinstance(st, dict):
                    apply_status(ks, st)
            except Exception:
                pass

            async def serial_reader():
                while True:
                    now = time.monotonic()
                    try:
                        for st in bridge.read_status_frames():
                            ls.last_bridge_frame_t = now
                            ls.pump_link = st.get("pump_link", 0)
                            ls.age_ms = st.get("age_ms", None)
                            ls.last_code = st.get("code", 0)
                            ls.err_flags = st.get("err_flags", 0)
                            status_event.set()
                    except Exception:
                        pass
                    await asyncio.sleep(0.005)

            serial_task = asyncio.create_task(serial_reader())

            log.info("drukmix: running")

            while True:
                now = time.monotonic()

                # cfg reload
                if now - last_cfg_check >= max(0.5, cfg.cfg_reload_s):
                    last_cfg_check = now
                    try:
                        m = os.path.getmtime(cfg.cfg_path)
                    except Exception:
                        m = 0.0
                    if m and m != last_cfg_mtime:
                        last_cfg_mtime = m
                        new_cfg = load_config(cfg.cfg_path)
                        new_cfg.cfg_path = cfg.cfg_path
                        cfg = new_cfg
                        filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
                        liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)
                        try:
                            bridge.send_set_maxlpm(cfg.pump_max_lpm)
                        except Exception:
                            pass
                        await maybe_respond("command", f"DrukMix: cfg reloaded (gain={cfg.flow_gain})")

                # link health
                bridge_ok = (ls.last_bridge_frame_t != 0.0) and ((now - ls.last_bridge_frame_t) < cfg.bridge_offline_timeout_s)
                pump_ok = bridge_ok and (ls.pump_link == 1) and (ls.age_ms is not None) and (ls.age_ms < int(cfg.pump_offline_timeout_s * 1000))

                # pump mode from err_flags
                mode = decode_mode(ls.err_flags)

                # transitions -> terminal messages
                if last_bridge_ok is None:
                    last_bridge_ok = bridge_ok
                if last_pump_ok is None:
                    last_pump_ok = pump_ok
                if last_mode is None:
                    last_mode = mode

                if cfg.ui_notify:
                    if last_bridge_ok and not bridge_ok:
                        await maybe_respond("error", "DrukMix: USB bridge offline")
                    if (not last_bridge_ok) and bridge_ok:
                        await maybe_respond("command", "DrukMix: USB bridge online")

                    if last_pump_ok and not pump_ok:
                        await maybe_respond("error", "DrukMix: pump offline (ESP-NOW)")
                    if (not last_pump_ok) and pump_ok:
                        await maybe_respond("command", "DrukMix: pump online")

                    if mode != last_mode:
                        if mode == "MANUAL_FWD":
                            await maybe_respond("command", "DrukMix: mode MANUAL FORWARD")
                        elif mode == "MANUAL_REV":
                            await maybe_respond("command", "DrukMix: mode MANUAL REVERSE")
                        else:
                            await maybe_respond("command", "DrukMix: mode AUTO")

                last_bridge_ok = bridge_ok
                last_pump_ok = pump_ok
                last_mode = mode

                # consume notifications
                for _ in range(200):
                    msg = mr.notify_nowait()
                    if not msg:
                        break

                    if msg.get("method") == "notify_status_update":
                        params = msg.get("params", [])
                        if params and isinstance(params[0], dict):
                            apply_status(ks, params[0])
                        continue

                    rc = parse_remote_call(msg)
                    if not rc:
                        continue
                    rmethod, params = rc

                    if rmethod == "drukmix_ping":
                        await maybe_respond("command", "DrukMix: ping OK", min_interval_s=0.0)

                    elif rmethod == "drukmix_status":
                        txt = (
                            f"DrukMix: mode={mode} pump_ok={int(pump_ok)} bridge_ok={int(bridge_ok)} "
                            f"age_ms={ls.age_ms} code={ls.last_code} err=0x{ls.err_flags:04x}"
                        )
                        await maybe_respond("command", txt, min_interval_s=0.0)

                    elif rmethod == "drukmix_set_gain":
                        clear = str(params.get("clear", "false")).lower() in ("1", "true", "yes", "on")
                        if clear:
                            ov.gain = None
                            await maybe_respond("command", f"DrukMix: gain=cfg({cfg.flow_gain})", min_interval_s=0.0)
                        else:
                            ov.gain = max(0.0, float(params.get("gain", cfg.flow_gain)))
                            await maybe_respond("command", f"DrukMix: gain={ov.gain}", min_interval_s=0.0)

                    elif rmethod == "drukmix_set_debug":
                        lvl = str(params.get("level", "info")).strip().lower()
                        if lvl in ("off", "info", "debug"):
                            ov.log_level = lvl
                            await maybe_respond("command", f"DrukMix: log_level={lvl}", min_interval_s=0.0)

                    elif rmethod == "drukmix_reload_cfg":
                        last_cfg_mtime = 0.0
                        await maybe_respond("command", "DrukMix: cfg reload requested", min_interval_s=0.0)

                    elif rmethod == "drukmix_flush":
                        req_lpm = float(params.get("lpm", cfg.pump_max_lpm))
                        dur = float(params.get("duration", 0.0))
                        req_lpm = clamp(req_lpm, 0.0, cfg.pump_max_lpm)
                        fs.active = True
                        fs.lpm = req_lpm
                        fs.until_t = (time.monotonic() + dur) if dur > 0 else 0.0

                        async def do_flush():
                            flags = FLAG_AUTO  # allow output
                            await burst_send(req_lpm, flags)
                            ok = True
                            if cfg.flush_confirm:
                                want = expected_code(req_lpm, cfg.pump_max_lpm)
                                ok = await confirm_applied(want, stop=False)
                                tries = 0
                                while (not ok) and tries < cfg.flush_confirm_retries:
                                    tries += 1
                                    await burst_send(req_lpm, flags)
                                    ok = await confirm_applied(want, stop=False)
                            await maybe_respond("command" if ok else "error", f"DrukMix: FLUSH {req_lpm:.3f} LPM", min_interval_s=0.0)

                        asyncio.create_task(do_flush())

                    elif rmethod == "drukmix_flush_stop":
                        fs.active = False
                        fs.lpm = 0.0
                        fs.until_t = 0.0

                        async def do_stop():
                            flags = FLAG_STOP
                            await burst_send(0.0, flags)
                            ok = True
                            if cfg.flush_confirm:
                                ok = await confirm_applied(0, stop=True)
                                tries = 0
                                while (not ok) and tries < cfg.flush_confirm_retries:
                                    tries += 1
                                    await burst_send(0.0, flags)
                                    ok = await confirm_applied(0, stop=True)
                            await maybe_respond("command" if ok else "error", "DrukMix: FLUSH STOP", min_interval_s=0.0)

                        asyncio.create_task(do_stop())

                # periodic poll fallback
                if time.monotonic() - last_poll_t >= poll_period():
                    last_poll_t = time.monotonic()
                    try:
                        res = await mr.call("printer.objects.query", {"objects": {
                            "print_stats": ["state"],
                            "idle_timeout": ["state"],
                            "pause_resume": ["is_paused"],
                            "gcode_move": ["extrude_factor"],
                            "motion_report": ["live_extruder_velocity"],
                            "webhooks": ["state", "state_message"],
                        }})
                        st = (res or {}).get("status") or {}
                        if isinstance(st, dict):
                            apply_status(ks, st)
                    except Exception:
                        pass

                # flush autostop by duration
                if fs.active and fs.until_t > 0.0 and time.monotonic() >= fs.until_t:
                    fs.active = False
                    fs.lpm = 0.0
                    fs.until_t = 0.0

                klippy_ready = (ks.klippy_state == "ready")
                printing = is_printing(ks)
                active_motion = printing and (not ks.is_paused) and klippy_ready

                # Safety pause conditions
                if printing and (not ks.is_paused):
                    if cfg.pause_on_pump_offline and (not pump_ok):
                        await pause_with_popup("DrukMix: pump offline")
                    elif cfg.pause_on_manual_during_print and (mode != "AUTO"):
                        await pause_with_popup("DrukMix: switch MANUAL during print (set to AUTO)")

                # Decide desired LPM and flags
                max_lpm = cfg.pump_max_lpm
                gain = eff_gain()

                if fs.active:
                    desired_lpm = clamp(fs.lpm, 0.0, max_lpm)
                    flags = FLAG_AUTO if desired_lpm > 0.0 else FLAG_STOP
                else:
                    if (not active_motion) or (mode != "AUTO"):
                        desired_lpm = 0.0
                        flags = FLAG_STOP
                    else:
                        vel = float(ks.live_extruder_velocity)
                        dead = max(0.0, cfg.retract_deadband_mm_s)
                        is_rev = vel < -dead

                        speed = abs(vel)
                        lpm = speed * liters_per_mm * 60.0
                        lpm *= max(0.0, float(ks.extrude_factor))
                        lpm *= max(0.0, (cfg.retract_gain if is_rev else gain))
                        lpm = clamp(lpm, 0.0, max_lpm)

                        # FWD-only min_run; no hold by default
                        if not is_rev:
                            if 0.0 < lpm < cfg.min_run_lpm:
                                lpm = cfg.min_run_lpm

                        desired_lpm = lpm
                        if desired_lpm <= 0.0:
                            flags = FLAG_STOP
                        else:
                            flags = FLAG_AUTO | (FLAG_REV if is_rev else 0)

                # Send to bridge periodically
                if time.monotonic() - last_send_t >= send_period():
                    last_send_t = time.monotonic()
                    try:
                        bridge.send_flow(desired_lpm, flags)
                    except Exception:
                        pass

                # Logging (periodic)
                lvl = eff_log_level()
                if lvl != "off":
                    do_log = (lvl == "debug") or ((time.monotonic() - last_log_t) >= max(0.5, cfg.log_period_s))
                    if do_log:
                        last_log_t = time.monotonic()
                        log.info(
                            f"drukmix: mode={'FLUSH' if fs.active else 'AUTO'} "
                            f"print={ks.print_state} idle={ks.idle_state} paused={int(ks.is_paused)} klippy={ks.klippy_state} "
                            f"vel={ks.live_extruder_velocity:.3f} ef={ks.extrude_factor:.3f} "
                            f"lpm={desired_lpm:.3f} flags=0x{flags:02x} "
                            f"bridge_ok={int(bridge_ok)} pump_ok={int(pump_ok)} age_ms={ls.age_ms} "
                            f"sw={mode} err=0x{ls.err_flags:04x}"
                        )

                await asyncio.sleep(0.01)

        except Exception as e:
            log.error(f"drukmix: error: {e}")
            try:
                if bridge and bridge.ser:
                    bridge.send_flow(0.0, FLAG_STOP)
            except Exception:
                pass
            try:
                if serial_task:
                    serial_task.cancel()
                    try:
                        await serial_task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if bridge:
                    bridge.close()
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
