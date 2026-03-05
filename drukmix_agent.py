#!/usr/bin/env python3
# DrukMix Moonraker Agent
# - Klipper macro -> Moonraker remote_method -> this agent -> USB bridge -> ESP-NOW -> Pump
#
# Ключові моменти:
# 1) РІВНО ОДНА корутина читає Moonraker websocket (демультиплексор id/notify), щоб не було “локів”.
# 2) drukmix.cfg дозволяє inline-коментарі після значення (key = 1.0  # comment) — агент це ковтає.
# 3) AUTO режим рахує LPM із motion_report.live_extruder_velocity (mm/s) та "віртуального філамента"
#    з filament_diameter у [extruder] (printer.cfg), помножено на extrude_factor та flow_gain.

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

# ---- USB protocol constants (must match bridge firmware) ----
PROTO = 1
USB_SET_FLOW = 1       # body: i32 milli_lpm, u8 flags
USB_SET_MAXLPM = 3     # body: i32 pump_max_milli_lpm
USB_BRIDGE_STATUS = 101
FLAG_STOP = 0x02


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


def parse_bridge_status(payload: bytes) -> Optional[Dict[str, Any]]:
    # payload: [proto,msg_type,seq,mono_ms] + body + crc
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

    # Мінімум, який використовує агент (узгодь з прошивкою bridge):
    # pump_link:u8 (0/1)
    # last_seen_div10:u16 (вік heartbeat насоса, одиниця 10мс; 65535=unknown)
    # ... (можуть бути інші поля)
    # applied_code:u8 (байт коду застосованого керування)
    #
    # У твоєму старому варіанті applied_code сидів на offset=5
    if len(body) < 6:
        return None

    pump_link = body[0]
    last_seen_div10 = struct.unpack_from("<H", body, 1)[0]
    applied_code = body[5]
    age_ms = None if last_seen_div10 == 65535 else int(last_seen_div10) * 10

    return {"pump_link": int(pump_link), "age_ms": age_ms, "code": int(applied_code)}


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

    printer_cfg: str
    filament_diameter_fallback: float

    update_hz: float
    poll_hz: float

    bridge_offline_timeout_s: float
    pump_offline_timeout_s: float
    pause_on_fault: bool
    pause_timeout_s: float
    ui_notify: bool

    log_file: str
    log_level: str
    log_period_s: float

    flush_burst_count: int
    flush_burst_interval_ms: int
    flush_confirm: bool
    flush_confirm_timeout_s: float
    flush_confirm_tolerance_code: int
    flush_confirm_retries: int

    cfg_reload_s: float
    cfg_path: str = ""


def _strip_inline_comment(v: str) -> str:
    # Дозволяємо:
    #   key = 1.23   # comment
    #   key = 1.23   ; comment
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
    # допускаємо "20.0" як int
    return int(float(_strip_inline_comment(raw)))


def _get_str(s: configparser.SectionProxy, key: str, default: str) -> str:
    raw = s.get(key, default)
    return _strip_inline_comment(raw)


def load_config(path: str) -> Cfg:
    # inline_comment_prefixes дозволяє ConfigParser ігнорувати коментарі після значення
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

        printer_cfg=_get_str(s, "printer_cfg", os.path.expanduser("~/printer_data/config/printer.cfg")),
        filament_diameter_fallback=_get_float(s, "filament_diameter_fallback", 35.0),

        update_hz=_get_float(s, "update_hz", 6.0),
        poll_hz=_get_float(s, "poll_hz", 0.5),

        bridge_offline_timeout_s=_get_float(s, "bridge_offline_timeout_s", 1.0),
        pump_offline_timeout_s=_get_float(s, "pump_offline_timeout_s", 1.2),
        pause_on_fault=get_bool("pause_on_fault", True),
        pause_timeout_s=_get_float(s, "pause_timeout_s", 2.0),
        ui_notify=get_bool("ui_notify", True),

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
    # Читаємо filament_diameter з [extruder]
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
    # L/mm = (π*(d/2)^2 mm^2) / 1_000_000 (mm^3 per liter)
    r = d / 2.0
    area_mm2 = math.pi * r * r
    return area_mm2 / 1_000_000.0


# ----------------- runtime state -----------------
@dataclasses.dataclass
class KlipperState:
    print_state: str = "unknown"      # print_stats.state: printing/paused/complete/standby/...
    idle_state: str = "unknown"       # idle_timeout.state: Printing/Ready/Idle
    is_paused: bool = False           # pause_resume.is_paused
    klippy_state: str = "unknown"     # webhooks.state: ready/shutdown/...
    extrude_factor: float = 1.0       # gcode_move.extrude_factor
    live_extruder_velocity: float = 0.0  # motion_report.live_extruder_velocity (mm/s)


@dataclasses.dataclass
class LinkState:
    last_bridge_frame_t: float = 0.0
    pump_link: int = 0
    age_ms: Optional[int] = None
    last_code: int = 0


@dataclasses.dataclass
class FlushState:
    active: bool = False
    lpm: float = 0.0
    until_t: float = 0.0


@dataclasses.dataclass
class Overrides:
    gain: Optional[float] = None
    pump_max_lpm: Optional[float] = None
    min_run_lpm: Optional[float] = None
    min_run_hold_s: Optional[float] = None
    log_level: Optional[str] = None  # off|info|debug


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


# ----------------- Moonraker client (single reader demux) -----------------
class MoonrakerClient:
    """
    ВАЖЛИВО:
    Рівно ОДНА корутина читає websocket.
    Відповіді з "id" -> pending Futures
    Нотифікації без id -> notify queue
    """
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

        # Реєструємо remote methods, які викликаються з Klipper макросів
        for m in (
            "drukmix_flush",
            "drukmix_flush_stop",
            "drukmix_set_gain",
            "drukmix_set_limits",
            "drukmix_set_debug",
            "drukmix_clear_overrides",
            "drukmix_reload_cfg",
            "drukmix_ping",
        ):
            await self.call("connection.register_remote_method", {"method_name": m})

        # Підписка на ключові об'єкти Klipper
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
            # Завалити всі pending, щоб call() не висів вічно
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
        # Відповідь у Mainsail terminal
        if level not in ("echo", "command", "error"):
            level = "echo"
        safe = msg.replace('"', "'")
        script = f'ReSPOND TYPE={level} MSG="{safe}"'.replace("ReSPOND", "RESPOND")
        await self.call("printer.gcode.script", {"script": script})

    async def pause_print(self):
        await self.call("printer.print.pause", {})


# ----------------- Bridge serial -----------------
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

    def send_flow(self, lpm: float, stop: bool):
        milli = int(lpm * 1000)
        flags = FLAG_STOP if stop else 0
        pkt = build_usb_packet(USB_SET_FLOW, self.seq, struct.pack("<iB", milli, flags))
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


def expected_code(lpm: float, max_lpm: float) -> int:
    if max_lpm <= 0:
        return 0
    c = int(round((clamp(lpm, 0.0, max_lpm) / max_lpm) * 255.0))
    return int(clamp(c, 0, 255))


def parse_remote_call(msg: dict) -> Optional[Tuple[str, dict]]:
    # Moonraker remote_method приходить як notification:
    # {"jsonrpc":"2.0","method":"drukmix_ping","params":{...}}
    m = msg.get("method")
    if not isinstance(m, str):
        return None
    if not m.startswith("drukmix_"):
        return None
    p = msg.get("params") or {}
    return (m, p) if isinstance(p, dict) else (m, {})


# ----------------- agent main -----------------
async def run_agent(cfg_path: str):
    cfg = load_config(cfg_path)
    if not cfg.enabled:
        print("drukmix: disabled")
        return

    log = setup_logger(cfg.log_file)

    # hard single-instance lock
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
    last_nonzero_t = 0.0

    last_bridge_ok = True
    last_pump_ok = True

    fault_since: Optional[float] = None
    paused_once = False

    last_info_log = 0.0
    last_debug_log = 0.0

    def eff_log_level() -> str:
        lvl = (ov.log_level or cfg.log_level or "info").lower()
        return lvl if lvl in ("off", "info", "debug") else "info"

    def eff_gain() -> float:
        return float(ov.gain) if ov.gain is not None else cfg.flow_gain

    def eff_pump_max_lpm() -> float:
        return float(ov.pump_max_lpm) if ov.pump_max_lpm is not None else cfg.pump_max_lpm

    def eff_min_run_lpm() -> float:
        return float(ov.min_run_lpm) if ov.min_run_lpm is not None else cfg.min_run_lpm

    def eff_min_run_hold_s() -> float:
        return float(ov.min_run_hold_s) if ov.min_run_hold_s is not None else cfg.min_run_hold_s

    def send_period() -> float:
        return 1.0 / max(cfg.update_hz, 0.5)

    def poll_period() -> float:
        return 1.0 / max(cfg.poll_hz, 0.1)

    def is_print_active() -> bool:
        # Сигнал “йде друк” може бути як:
        #  - print_stats.state == "printing"
        #  - idle_timeout.state == "Printing"
        ps = ks.print_state.lower()
        it = ks.idle_state.lower()
        return (ps == "printing") or (it == "printing")

    async def log_line(line: str):
        nonlocal last_info_log, last_debug_log
        lvl = eff_log_level()
        now = time.monotonic()
        if lvl == "off":
            return
        if lvl == "debug":
            if now - last_debug_log >= 1.0:
                last_debug_log = now
                log.info(line)
            return
        if now - last_info_log >= max(0.5, cfg.log_period_s):
            last_info_log = now
            log.info(line)

    async def burst_send(bridge: BridgeSerial, lpm: float, stop: bool):
        count = max(1, int(cfg.flush_burst_count))
        interval = max(0.0, float(cfg.flush_burst_interval_ms)) / 1000.0
        for _ in range(count):
            try:
                bridge.send_flow(lpm, stop=stop)
            except Exception:
                pass
            if interval > 0:
                await asyncio.sleep(interval)

    async def confirm_applied(target_lpm: float, stop: bool) -> bool:
        max_lpm = eff_pump_max_lpm()
        want = 0 if stop else expected_code(target_lpm, max_lpm)
        tol = int(clamp(cfg.flush_confirm_tolerance_code, 0, 50))
        deadline = time.monotonic() + max(0.05, cfg.flush_confirm_timeout_s)

        while time.monotonic() < deadline:
            if stop:
                if ls.last_code == 0:
                    return True
            else:
                if abs(ls.last_code - want) <= tol:
                    return True

            status_event.clear()
            try:
                await asyncio.wait_for(status_event.wait(), timeout=0.10)
            except asyncio.TimeoutError:
                pass
        return False

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

            # застосувати max_lpm у bridge при старті (override має пріоритет)
            bridge.send_set_maxlpm(eff_pump_max_lpm())

            # стартовий snapshot (щоб не чекати нотифікацій)
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

            log.info("drukmix: running")

            async def serial_reader():
                while True:
                    now = time.monotonic()
                    try:
                        for st in bridge.read_status_frames():
                            ls.last_bridge_frame_t = now
                            ls.pump_link = st.get("pump_link", 0)
                            ls.age_ms = st.get("age_ms", None)
                            ls.last_code = st.get("code", 0)
                            status_event.set()
                    except Exception:
                        pass
                    await asyncio.sleep(0.005)

            serial_task = asyncio.create_task(serial_reader())

            while True:
                now = time.monotonic()

                # cfg reload (base values only; overrides stay)
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

                        if ov.pump_max_lpm is None:
                            try:
                                bridge.send_set_maxlpm(cfg.pump_max_lpm)
                            except Exception:
                                pass

                        if cfg.ui_notify:
                            try:
                                await mr.respond("command", f"DrukMix: cfg reloaded (gain={cfg.flow_gain})")
                            except Exception:
                                pass

                # link health
                bridge_ok = (ls.last_bridge_frame_t != 0.0) and ((now - ls.last_bridge_frame_t) < cfg.bridge_offline_timeout_s)
                pump_ok = (
                    bridge_ok
                    and (ls.pump_link == 1)
                    and (ls.age_ms is not None)
                    and (ls.age_ms < int(cfg.pump_offline_timeout_s * 1000))
                )

                # UI transitions
                if cfg.ui_notify:
                    if last_bridge_ok and not bridge_ok:
                        try: await mr.respond("error", "DrukMix: USB bridge offline")
                        except Exception: pass
                    if (not last_bridge_ok) and bridge_ok:
                        try: await mr.respond("echo", "DrukMix: USB bridge online")
                        except Exception: pass
                    if last_pump_ok and not pump_ok:
                        try: await mr.respond("error", "DrukMix: pump offline (ESP-NOW)")
                        except Exception: pass
                    if (not last_pump_ok) and pump_ok:
                        try: await mr.respond("echo", "DrukMix: pump online")
                        except Exception: pass
                last_bridge_ok = bridge_ok
                last_pump_ok = pump_ok

                # consume notifications fast (remote calls + status updates)
                for _ in range(200):
                    msg = mr.notify_nowait()
                    if not msg:
                        break

                    # status updates from subscribe
                    if msg.get("method") == "notify_status_update":
                        params = msg.get("params", [])
                        if params and isinstance(params[0], dict):
                            apply_status(ks, params[0])
                        continue

                    rc = parse_remote_call(msg)
                    if not rc:
                        continue
                    rmethod, params = rc
                    log.info(f"drukmix: got remote {rmethod} params={params}")

                    if rmethod == "drukmix_ping":
                        if cfg.ui_notify:
                            try: await mr.respond("command", "DrukMix: ping OK")
                            except Exception: pass

                    elif rmethod == "drukmix_flush":
                        req_lpm = float(params.get("lpm", eff_pump_max_lpm()))
                        dur = float(params.get("duration", 0.0))
                        req_lpm = clamp(req_lpm, 0.0, eff_pump_max_lpm())
                        fs.active = True
                        fs.lpm = req_lpm
                        fs.until_t = (now + dur) if dur > 0 else 0.0

                        async def do_flush():
                            await burst_send(bridge, req_lpm, stop=False)
                            ok = True
                            if cfg.flush_confirm:
                                ok = await confirm_applied(req_lpm, stop=False)
                                tries = 0
                                while (not ok) and tries < cfg.flush_confirm_retries:
                                    tries += 1
                                    await burst_send(bridge, req_lpm, stop=False)
                                    ok = await confirm_applied(req_lpm, stop=False)
                            if cfg.ui_notify:
                                try:
                                    await mr.respond("command" if ok else "error", f"DrukMix: FLUSH {req_lpm:.3f} LPM")
                                except Exception:
                                    pass

                        asyncio.create_task(do_flush())

                    elif rmethod == "drukmix_flush_stop":
                        fs.active = False
                        fs.lpm = 0.0
                        fs.until_t = 0.0

                        async def do_stop():
                            await burst_send(bridge, 0.0, stop=True)
                            ok = True
                            if cfg.flush_confirm:
                                ok = await confirm_applied(0.0, stop=True)
                                tries = 0
                                while (not ok) and tries < cfg.flush_confirm_retries:
                                    tries += 1
                                    await burst_send(bridge, 0.0, stop=True)
                                    ok = await confirm_applied(0.0, stop=True)
                            if cfg.ui_notify:
                                try:
                                    await mr.respond("command" if ok else "error", "DrukMix: FLUSH STOP")
                                except Exception:
                                    pass

                        asyncio.create_task(do_stop())

                    elif rmethod == "drukmix_set_gain":
                        clear = str(params.get("clear", "false")).lower() in ("1", "true", "yes", "on")
                        if clear:
                            ov.gain = None
                            if cfg.ui_notify:
                                try: await mr.respond("command", f"DrukMix: gain=cfg({cfg.flow_gain})")
                                except Exception: pass
                        else:
                            ov.gain = max(0.0, float(params.get("gain", cfg.flow_gain)))
                            if cfg.ui_notify:
                                try: await mr.respond("command", f"DrukMix: gain={ov.gain}")
                                except Exception: pass

                    elif rmethod == "drukmix_set_limits":
                        if "pump_max_lpm" in params:
                            ov.pump_max_lpm = max(0.1, float(params["pump_max_lpm"]))
                            try: bridge.send_set_maxlpm(eff_pump_max_lpm())
                            except Exception: pass
                        if "min_run_lpm" in params:
                            ov.min_run_lpm = max(0.0, float(params["min_run_lpm"]))
                        if "min_run_hold_s" in params:
                            ov.min_run_hold_s = max(0.0, float(params["min_run_hold_s"]))
                        if cfg.ui_notify:
                            try: await mr.respond("command", "DrukMix: limits updated (override)")
                            except Exception: pass

                    elif rmethod == "drukmix_set_debug":
                        lvl = str(params.get("level", "info")).strip().lower()
                        if lvl in ("off", "info", "debug"):
                            ov.log_level = lvl
                            if cfg.ui_notify:
                                try: await mr.respond("command", f"DrukMix: log_level={lvl}")
                                except Exception: pass

                    elif rmethod == "drukmix_clear_overrides":
                        ov = Overrides()
                        try: bridge.send_set_maxlpm(cfg.pump_max_lpm)
                        except Exception: pass
                        if cfg.ui_notify:
                            try: await mr.respond("command", "DrukMix: overrides cleared (cfg active)")
                            except Exception: pass

                    elif rmethod == "drukmix_reload_cfg":
                        last_cfg_mtime = 0.0
                        if cfg.ui_notify:
                            try: await mr.respond("command", "DrukMix: cfg reload requested")
                            except Exception: pass

                # periodic poll (повільний fallback)
                if now - last_poll_t >= poll_period():
                    last_poll_t = now
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

                # flush duration autostop
                if fs.active and fs.until_t > 0.0 and now >= fs.until_t:
                    fs.active = False
                    fs.lpm = 0.0
                    fs.until_t = 0.0
                    asyncio.create_task(burst_send(bridge, 0.0, stop=True))

                klippy_ready = (ks.klippy_state == "ready")
                printing = is_print_active()
                active_motion = printing and (not ks.is_paused)

                max_lpm = eff_pump_max_lpm()
                min_run = eff_min_run_lpm()
                hold_s = eff_min_run_hold_s()
                gain = eff_gain()

                # ---- desired_lpm computation ----
                if fs.active:
                    desired_lpm = clamp(fs.lpm, 0.0, max_lpm)
                else:
                    if (not klippy_ready) or (not active_motion):
                        desired_lpm = 0.0
                    else:
                        vel = max(0.0, float(ks.live_extruder_velocity))  # mm/s
                        # LPM = (mm/s) * (L/mm) * 60
                        desired_lpm = vel * liters_per_mm * 60.0
                        desired_lpm *= max(0.0, float(ks.extrude_factor))
                        desired_lpm *= max(0.0, float(gain))
                        desired_lpm = clamp(desired_lpm, 0.0, max_lpm)

                        if desired_lpm > 0.0:
                            last_nonzero_t = now

                        # min_run clamp
                        if 0.0 < desired_lpm < min_run:
                            desired_lpm = min_run

                        # hold after stopping extrusion
                        if desired_lpm == 0.0 and (now - last_nonzero_t) < hold_s:
                            desired_lpm = min_run

                # ---- send to bridge ----
                if now - last_send_t >= send_period():
                    last_send_t = now
                    try:
                        bridge.send_flow(desired_lpm, stop=(desired_lpm <= 0.0))
                    except Exception:
                        pass

                # ---- pause on fault (AUTO only) ----
                if (not fs.active) and active_motion and klippy_ready and cfg.pause_on_fault and (not pump_ok):
                    if fault_since is None:
                        fault_since = now
                        paused_once = False
                    elif (not paused_once) and (now - fault_since) >= cfg.pause_timeout_s:
                        paused_once = True
                        try:
                            await mr.pause_print()
                            if cfg.ui_notify:
                                await mr.respond("error", "DrukMix: paused (pump offline)")
                        except Exception:
                            pass
                else:
                    fault_since = None
                    paused_once = False

                await log_line(
                    f"drukmix: mode={'FLUSH' if fs.active else 'AUTO'} "
                    f"print={ks.print_state} idle={ks.idle_state} paused={int(ks.is_paused)} "
                    f"klippy={ks.klippy_state} vel={ks.live_extruder_velocity:.3f} ef={ks.extrude_factor:.3f} "
                    f"gain={gain:.3f} lpm={desired_lpm:.3f} code={ls.last_code} "
                    f"bridge_ok={int(bridge_ok)} pump_ok={int(pump_ok)} age_ms={ls.age_ms}"
                )

                await asyncio.sleep(0.01)

        except Exception as e:
            log.error(f"drukmix: error: {e}")

            # failsafe stop
            try:
                if bridge and bridge.ser:
                    bridge.send_flow(0.0, stop=True)
            except Exception:
                pass

            try:
                if serial_task:
                    serial_task.cancel()
                    try:
                        await serial_task
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
