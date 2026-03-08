#!/usr/bin/env python3
import asyncio
import configparser
import dataclasses
import json
import logging
import os
import struct
import time
import fcntl
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

import serial
import websockets


# ---------------- USB bridge protocol ----------------
PROTO = 1
USB_SET_FLOW = 1
USB_PING = 2
USB_SET_MAXLPM = 3
USB_RESET_FAULT = 4
USB_BRIDGE_STATUS = 101

FLAG_REV = 0x01
FLAG_STOP = 0x02
FLAG_AUTO = 0x04


# ---------------- config ----------------
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
    log_file: str
    log_level: str
    cfg_reload_s: float
    cfg_path: str = ""


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
        serial_port=_get_str(s, "serial_port", ""),
        serial_baud=_get_int(s, "serial_baud", 921600),
        client_name=_get_str(s, "client_name", "drukmix"),
        client_version=_get_str(s, "client_version", "3.0.0-baseline"),
        client_type=_get_str(s, "client_type", "agent"),
        client_url=_get_str(s, "client_url", "https://drukos.local/drukmix"),
        log_file=_get_str(s, "log_file", os.path.expanduser("~/printer_data/logs/drukmix.log")),
        log_level=_get_str(s, "log_level", "info").lower(),
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


# ---------------- low-level helpers ----------------
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
    i = 0
    n = len(frame)
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


# ---------------- serial bridge ----------------
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


# ---------------- Moonraker ----------------
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

    async def register_methods(self, names):
        for name in names:
            await self.call("connection.register_remote_method", {"method_name": name})

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


# ---------------- app helpers ----------------
async def mr_respond(mr: MoonrakerClient, msg: str, level: str = "command"):
    try:
        await mr.respond(level, msg)
    except Exception:
        pass


def build_status_text(last_status: Dict[str, Any], age_ms: int) -> str:
    return (
        "DrukMix: "
        f"bridge_status=1 "
        f"pump_link={int(last_status.get('pump_link', 0))} "
        f"pump_online={int(last_status.get('pump_online', 0))} "
        f"pump_running={int(last_status.get('pump_running', 0))} "
        f"state={last_status.get('pump_state')} "
        f"fault={last_status.get('pump_fault_code')} "
        f"target={last_status.get('target_milli_lpm')} "
        f"actual={last_status.get('actual_milli_lpm')} "
        f"code={last_status.get('applied_code')} "
        f"age_ms={age_ms}"
    )


# ---------------- main ----------------
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
        log.error("drukmix: another instance is running")
        return

    method_names = (
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
    )

    mr = None
    bridge = None
    backoff = 0.5

    last_status: Dict[str, Any] = {}
    last_status_t = 0.0
    last_cfg_check_t = 0.0
    last_cfg_mtime = 0.0

    while True:
        try:
            cfg = load_config(cfg_path)

            bridge = BridgeSerial(cfg.serial_port, cfg.serial_baud)
            bridge.open()

            mr = MoonrakerClient(cfg.moonraker_ws, cfg)
            await mr.connect()
            await mr.register_methods(method_names)

            log.info("drukmix: connected")

            backoff = 0.5

            while True:
                now = time.monotonic()

                if now - last_cfg_check_t >= max(0.5, cfg.cfg_reload_s):
                    last_cfg_check_t = now
                    try:
                        mtime = os.path.getmtime(cfg.cfg_path)
                    except Exception:
                        mtime = 0.0
                    if mtime and mtime != last_cfg_mtime:
                        last_cfg_mtime = mtime
                        cfg = load_config(cfg.cfg_path)
                        log.info("drukmix: cfg reloaded")

                for st in bridge.read_status_frames():
                    last_status = st
                    last_status_t = time.monotonic()

                for _ in range(50):
                    msg = mr.notify_nowait()
                    if not msg:
                        break

                    method = msg.get("method")

                    if method == "drukmix_ping":
                        await mr_respond(mr, "DrukMix: ping OK")
                        continue

                    if method == "drukmix_status":
                        age = -1
                        if last_status_t > 0.0:
                            age = int((time.monotonic() - last_status_t) * 1000)

                        if last_status:
                            await mr_respond(mr, build_status_text(last_status, age))
                        else:
                            await mr_respond(mr, "DrukMix: no bridge status yet", level="error")
                        continue

                    if method == "drukmix_reset_fault":
                        params = msg.get("params") or {}
                        if not isinstance(params, dict):
                            params = {}
                        try:
                            bridge.reset_fault(int(params.get("selector", 0)))
                            await mr_respond(mr, "DrukMix: reset fault request sent")
                        except Exception:
                            await mr_respond(mr, "DrukMix: reset fault request failed", level="error")
                        continue

                    if isinstance(method, str) and method.startswith("drukmix_"):
                        await mr_respond(mr, f"DrukMix: method {method} disabled in baseline build", level="error")

                await asyncio.sleep(0.02)

        except Exception as e:
            log.error(f"drukmix: error: {e}")

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
