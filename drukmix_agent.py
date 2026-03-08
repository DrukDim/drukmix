#!/usr/bin/env python3
import asyncio
import configparser
import dataclasses
import json
import logging
import math
import os
import re
import struct
import time
import fcntl
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Tuple

import serial
import websockets


PROTO = 1
USB_SET_FLOW = 1
USB_PING = 2
USB_SET_MAXLPM = 3
USB_RESET_FAULT = 4
USB_BRIDGE_STATUS = 101

FLAG_REV = 0x01
FLAG_STOP = 0x02
FLAG_AUTO = 0x04

EF_MANUAL_FWD = 0x0010
EF_MANUAL_REV = 0x0020
EF_AUTO_ALLOWED = 0x0040
EF_AUTO_ACTIVE = 0x0080
EF_DIR_ASSERTED = 0x0100
EF_WIPER_TPL = 0x0200


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

    pause_on_pump_offline: bool
    pause_on_manual_during_print: bool
    ui_notify: bool

    bridge_offline_timeout_s: float
    pump_offline_timeout_s: float

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

    def get_bool(k: str, d: bool = False) -> bool:
        raw = s.get(k, str(d))
        raw = _strip_inline_comment(raw).lower()
        return raw in ("1", "true", "yes", "on")

    return Cfg(
        enabled=get_bool("enabled", True),
        moonraker_ws=_get_str(s, "moonraker_ws", "ws://127.0.0.1:7125/websocket"),
        serial_port=_get_str(s, "serial_port", ""),
        serial_baud=_get_int(s, "serial_baud", 921600),

        client_name=_get_str(s, "client_name", "drukmix"),
        client_version=_get_str(s, "client_version", "3.1.0-pumpvfd"),
        client_type=_get_str(s, "client_type", "agent"),
        client_url=_get_str(s, "client_url", "https://drukos.local/drukmix"),

        pump_max_lpm=_get_float(s, "pump_max_lpm", 10.0),
        min_run_lpm=_get_float(s, "min_run_lpm", 0.20),
        min_run_hold_s=_get_float(s, "min_run_hold_s", 0.0),
        flow_gain=_get_float(s, "flow_gain", 1.0),

        retract_deadband_mm_s=_get_float(s, "retract_deadband_mm_s", 0.20),
        retract_gain=_get_float(s, "retract_gain", 1.0),

        printer_cfg=_get_str(s, "printer_cfg", os.path.expanduser("~/printer_data/config/printer.cfg")),
        filament_diameter_fallback=_get_float(s, "filament_diameter_fallback", 35.0),

        update_hz=_get_float(s, "update_hz", 6.0),
        poll_hz=_get_float(s, "poll_hz", 0.5),

        pause_on_pump_offline=get_bool("pause_on_pump_offline", True),
        pause_on_manual_during_print=get_bool("pause_on_manual_during_print", False),
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
            "drukmix_set_limits",
            "drukmix_clear_overrides",
            "drukmix_set_debug",
            "drukmix_reload_cfg",
            "drukmix_reset_fault",
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
    if len(body) < 32:
        return None

    off = 0
    pump_link = body[off]; off += 1
    last_seen_div10 = struct.unpack_from("<H", body, off)[0]; off += 2
    last_ack_seq = struct.unpack_from("<H", body, off)[0]; off += 2
    applied_code = body[off]; off += 1
    err_flags = struct.unpack_from("<H", body, off)[0]; off += 2
    retry_count = struct.unpack_from("<H", body, off)[0]; off += 2
    send_fail_count = struct.unpack_from("<H", body, off)[0]; off += 2
    pump_max_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4

    pump_state = struct.unpack_from("<H", body, off)[0]; off += 2
    pump_fault_code = struct.unpack_from("<H", body, off)[0]; off += 2
    pump_online = body[off]; off += 1
    pump_running = body[off]; off += 1
    target_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4
    actual_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4
    hw_setpoint_raw = struct.unpack_from("<i", body, off)[0]; off += 4
    pump_flags = struct.unpack_from("<H", body, off)[0]; off += 2

    age_ms = None if last_seen_div10 == 65535 else int(last_seen_div10) * 10

    return {
        "resp_seq": int(seq),
        "mono_ms": int(mono_ms),
        "pump_link": int(pump_link),
        "age_ms": age_ms,
        "last_seen_div10": int(last_seen_div10),
        "last_ack_seq": int(last_ack_seq),
        "applied_code": int(applied_code),
        "code": int(applied_code),
        "err_flags": int(err_flags),
        "retry_count": int(retry_count),
        "send_fail_count": int(send_fail_count),
        "pump_max_milli_lpm": int(pump_max_milli_lpm),
        "pump_state": int(pump_state),
        "pump_fault_code": int(pump_fault_code),
        "pump_online": bool(pump_online),
        "pump_running": bool(pump_running),
        "target_milli_lpm": int(target_milli_lpm),
        "actual_milli_lpm": int(actual_milli_lpm),
        "hw_setpoint_raw": int(hw_setpoint_raw),
        "pump_flags": int(pump_flags),
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

    def _next_seq(self) -> int:
        seq = self.seq
        self.seq = (self.seq + 1) & 0xFFFF
        if self.seq == 0:
            self.seq = 1
        return seq

    def send_set_maxlpm(self, pump_max_lpm: float):
        milli = int(pump_max_lpm * 1000)
        pkt = build_usb_packet(USB_SET_MAXLPM, self._next_seq(), struct.pack("<i", milli))
        self.ser.write(pkt)

    def send_flow(self, lpm: float, flags: int):
        milli = int(lpm * 1000)
        pkt = build_usb_packet(USB_SET_FLOW, self._next_seq(), struct.pack("<iB", milli, flags & 0xFF))
        self.ser.write(pkt)

    def reset_fault(self, selector: int = 0):
        pkt = build_usb_packet(USB_RESET_FAULT, self._next_seq(), struct.pack("<H", int(selector) & 0xFFFF))
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


def expected_code(lpm: float, max_lpm: float) -> int:
    if max_lpm <= 0:
        return 0
    c = int(round((clamp(lpm, 0.0, max_lpm) / max_lpm) * 255.0))
    return int(clamp(c, 0, 255))


async def run_agent(cfg_path: str):
    cfg = load_config(cfg_path)
    if not cfg.enabled:
        print("drukmix: disabled")
        return

    log = setup_logger(cfg.log_file)

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

    last_bridge_ok = None
    last_pump_ok = None
    last_mode = None
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

    log.info(f"drukmix: start filament_d={filament_d} liters/mm={liters_per_mm:.6f} gain={cfg.flow_gain}")

    backoff = 0.5
    while True:
        mr = None
        bridge = None
        serial_task = None
        try:
            cfg = load_config(cfg_path)
            filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
            liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)

            bridge = BridgeSerial(cfg.serial_port, cfg.serial_baud)
            bridge.open()
            bridge.send_set_maxlpm(cfg.pump_max_lpm)

            mr = MoonrakerClient(cfg.moonraker_ws, cfg)
            await mr.connect()

            async def serial_reader():
                while True:
                    try:
                        frames = bridge.read_status_frames()
                        if not frames:
                            await asyncio.sleep(0.01)
                            continue
                        now = time.monotonic()
                        for st in frames:
                            ls.last_bridge_frame_t = now
                            ls.pump_link = int(st.get("pump_link", 0))
                            ls.age_ms = st.get("age_ms")
                            ls.last_code = int(st.get("code", 0))
                            ls.err_flags = int(st.get("err_flags", 0))
                            status_event.set()
                    except Exception:
                        await asyncio.sleep(0.05)

            serial_task = asyncio.create_task(serial_reader())
            log.info("drukmix: running")

            while True:
                now = time.monotonic()

                if now - last_cfg_check >= max(0.2, cfg.cfg_reload_s):
                    last_cfg_check = now
                    try:
                        mtime = os.path.getmtime(cfg.cfg_path)
                    except Exception:
                        mtime = 0.0
                    if mtime != last_cfg_mtime:
                        last_cfg_mtime = mtime
                        cfg = load_config(cfg.cfg_path)
                        filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
                        liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)
                        try:
                            bridge.send_set_maxlpm(cfg.pump_max_lpm)
                        except Exception:
                            pass
                        await maybe_respond("command", f"DrukMix: cfg reloaded (gain={cfg.flow_gain})")

                bridge_ok = (ls.last_bridge_frame_t != 0.0) and ((now - ls.last_bridge_frame_t) < cfg.bridge_offline_timeout_s)
                pump_ok = bridge_ok and (ls.age_ms is not None) and (ls.age_ms < int(cfg.pump_offline_timeout_s * 1000.0))
                mode = decode_mode(ls.err_flags)

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

                    elif rmethod == "drukmix_set_limits":
                        changed = []
                        if "pump_max_lpm" in params:
                            cfg.pump_max_lpm = max(0.0, float(params["pump_max_lpm"]))
                            try:
                                bridge.send_set_maxlpm(cfg.pump_max_lpm)
                            except Exception:
                                pass
                            changed.append(f"MAX_LPM={cfg.pump_max_lpm}")
                        if "min_run_lpm" in params:
                            cfg.min_run_lpm = max(0.0, float(params["min_run_lpm"]))
                            changed.append(f"MIN_LPM={cfg.min_run_lpm}")
                        if "min_run_hold_s" in params:
                            cfg.min_run_hold_s = max(0.0, float(params["min_run_hold_s"]))
                            changed.append(f"HOLD_S={cfg.min_run_hold_s}")
                        if changed:
                            await maybe_respond("command", "DrukMix: " + " ".join(changed), min_interval_s=0.0)
                        else:
                            await maybe_respond("command", "DrukMix: no limits changed", min_interval_s=0.0)

                    elif rmethod == "drukmix_clear_overrides":
                        ov.gain = None
                        ov.log_level = None
                        cfg = load_config(cfg.cfg_path)
                        filament_d = read_filament_diameter_from_printer_cfg(cfg.printer_cfg, cfg.filament_diameter_fallback)
                        liters_per_mm = liters_per_mm_from_diameter_mm(filament_d)
                        try:
                            bridge.send_set_maxlpm(cfg.pump_max_lpm)
                        except Exception:
                            pass
                        await maybe_respond("command", "DrukMix: overrides cleared", min_interval_s=0.0)

                    elif rmethod == "drukmix_set_debug":
                        lvl = str(params.get("level", "info")).strip().lower()
                        if lvl in ("off", "info", "debug"):
                            ov.log_level = lvl
                            await maybe_respond("command", f"DrukMix: log_level={lvl}", min_interval_s=0.0)

                    elif rmethod == "drukmix_reload_cfg":
                        last_cfg_mtime = 0.0
                        await maybe_respond("command", "DrukMix: cfg reload requested", min_interval_s=0.0)

                    elif rmethod == "drukmix_reset_fault":
                        try:
                            bridge.reset_fault(int(params.get("selector", 0)))
                            await maybe_respond("command", "DrukMix: reset fault request sent", min_interval_s=0.0)
                        except Exception:
                            await maybe_respond("error", "DrukMix: reset fault request failed", min_interval_s=0.0)

                    elif rmethod == "drukmix_flush":
                        req_lpm = float(params.get("lpm", cfg.pump_max_lpm))
                        dur = float(params.get("duration", 0.0))
                        req_lpm = clamp(req_lpm, 0.0, cfg.pump_max_lpm)
                        fs.active = True
                        fs.lpm = req_lpm
                        fs.until_t = (time.monotonic() + dur) if dur > 0 else 0.0

                        async def do_flush():
                            flags = FLAG_AUTO
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

                if time.monotonic() - last_poll_t >= poll_period():
                    last_poll_t = time.monotonic()
                    try:
                        res = await mr.call("printer.objects.query", {
                            "objects": {
                                "print_stats": ["state"],
                                "idle_timeout": ["state"],
                                "pause_resume": ["is_paused"],
                                "gcode_move": ["extrude_factor"],
                                "motion_report": ["live_extruder_velocity"],
                                "webhooks": ["state", "state_message"],
                            }
                        })
                        st = res.get("status", {}) if isinstance(res, dict) else {}
                        if isinstance(st, dict):
                            apply_status(ks, st)
                    except Exception:
                        pass

                if fs.active and fs.until_t > 0.0 and time.monotonic() >= fs.until_t:
                    fs.active = False
                    fs.lpm = 0.0
                    fs.until_t = 0.0

                printing = is_printing(ks)
                klippy_ready = (ks.klippy_state.lower() == "ready")
                active_motion = printing and (not ks.is_paused) and klippy_ready

                if printing and (not ks.is_paused):
                    if cfg.pause_on_pump_offline and (not pump_ok):
                        await pause_with_popup("DrukMix: pump offline")
                    elif cfg.pause_on_manual_during_print and (mode != "AUTO"):
                        await pause_with_popup("DrukMix: switch MANUAL during print (set to AUTO)")

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

                        if not is_rev and 0.0 < lpm < cfg.min_run_lpm:
                            lpm = cfg.min_run_lpm

                        desired_lpm = lpm
                        if desired_lpm <= 0.0:
                            flags = FLAG_STOP
                        else:
                            flags = FLAG_AUTO | (FLAG_REV if is_rev else 0)

                if time.monotonic() - last_send_t >= send_period():
                    last_send_t = time.monotonic()
                    try:
                        bridge.send_flow(desired_lpm, flags)
                    except Exception:
                        pass

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
