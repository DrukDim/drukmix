#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import configparser
import dataclasses
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

import websockets

from backend.backend_pumptpl import PumpTplBackend
from backend.backend_pumpvfd import PumpVfdBackend
from backend.bridge_usb_transport import BridgeUsbTransport

CONTROLLER_FIELDS = [
    "state",
    "target_pct",
    "rev",
    "reason",
    "t_start_s",
    "t_stop_s",
    "v_mms",
    "available",
    "stale",
]

DEFAULT_CFG_PATH = os.path.expanduser("~/printer_data/config/drukmix_agent.cfg")


@dataclasses.dataclass
class Cfg:
    enabled: bool
    moonraker_ws: str
    backend: str
    serial_port: str
    serial_baud: int
    update_hz: float
    status_timeout_s: float
    ui_notify: bool
    log_file: str
    log_level: str
    debug_log: bool
    debug_log_period_s: float
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


def load_cfg(path: str) -> Cfg:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not cp.read(path):
        raise FileNotFoundError(path)
    s = cp["drukmix_agent"]

    def get_bool(k: str, d: bool = False) -> bool:
        raw = _strip_inline_comment(s.get(k, str(d))).lower()
        return raw in ("1", "true", "yes", "on")

    return Cfg(
        enabled=get_bool("enabled", True),
        moonraker_ws=_get_str(s, "moonraker_ws", "ws://127.0.0.1:7125/websocket"),
        backend=_get_str(s, "backend", "pumpvfd"),
        serial_port=_get_str(s, "serial_port", "/dev/drukos-bridge"),
        serial_baud=_get_int(s, "serial_baud", 921600),
        update_hz=_get_float(s, "update_hz", 6.0),
        status_timeout_s=_get_float(s, "status_timeout_s", 2.0),
        ui_notify=get_bool("ui_notify", True),
        log_file=_get_str(
            s, "log_file", os.path.expanduser("~/printer_data/logs/drukmix_driver.log")
        ),
        log_level=_get_str(s, "log_level", "info").lower(),
        debug_log=get_bool("debug_log", False),
        debug_log_period_s=_get_float(s, "debug_log_period_s", 1.0),
        cfg_path=path,
    )


def setup_logger(log_file: str, log_level: str = "info") -> logging.Logger:
    lg = logging.getLogger("drukmix_driver")
    level_name = str(log_level or "info").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    lg.setLevel(level)
    lg.handlers.clear()

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    fh = RotatingFileHandler(log_file, maxBytes=3_000_000, backupCount=3)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    fh.setLevel(level)
    lg.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(level)
    lg.addHandler(sh)
    return lg


class MoonrakerClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._notify_q: asyncio.Queue = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._reader_task = None
        self._closed = False

    async def connect(self):
        self._ws = await websockets.connect(
            self.ws_url, ping_interval=20, ping_timeout=20
        )
        self._reader_task = asyncio.create_task(self._reader_loop())

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
                            fut.set_exception(
                                RuntimeError(f"Moonraker RPC error: {msg['error']}")
                            )
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


@dataclasses.dataclass
class ControllerStatus:
    state: str = "blocked"
    target_pct: float = 0.0
    rev: bool = False
    reason: str = "unknown"
    available: bool = False
    stale: bool = True
    last_t: float = 0.0


class Driver:
    def __init__(self, cfg: Cfg, log: logging.Logger):
        self.cfg = cfg
        self.log = log
        self.mr: Optional[MoonrakerClient] = None
        self.backend = None
        self.flush_until: float = 0.0
        self.flush_pct: float = 0.0
        self.flush_rev: bool = False
        self.status = ControllerStatus()
        self._last_debug_t: float = 0.0

    async def start(self):
        transport = BridgeUsbTransport(self.cfg.serial_port, self.cfg.serial_baud)
        if self.cfg.backend == "pumptpl":
            self.backend = PumpTplBackend(transport)
        else:
            self.backend = PumpVfdBackend(transport)

        self.backend.open()
        self.mr = MoonrakerClient(self.cfg.moonraker_ws)
        await self.mr.connect()

        await self._register_methods()
        await self._subscribe_controller()
        await self._initial_query()

        await self._loop()

    async def _register_methods(self):
        for m in (
            "drukmix_ping",
            "drukmix_status",
            "drukmix_stop",
            "drukmix_flush",
            "drukmix_reset_fault",
        ):
            try:
                await self.mr.call(
                    "connection.register_remote_method", {"method_name": m}
                )
            except Exception:
                # Compatibility: ignore if not supported
                break

    async def _subscribe_controller(self):
        await self.mr.call(
            "printer.objects.subscribe",
            {"objects": {"drukmix_controller": CONTROLLER_FIELDS}},
        )

    async def _initial_query(self):
        try:
            res = await self.mr.call(
                "printer.objects.query",
                {"objects": {"drukmix_controller": CONTROLLER_FIELDS}},
            )
            if isinstance(res, dict):
                st = res.get("status", {}).get("drukmix_controller")
                if isinstance(st, dict):
                    self._apply_controller_status(st, time.monotonic())
        except Exception as e:
            self.log.warning(f"initial query failed: {e}")

    def _apply_controller_status(self, st: Dict[str, Any], now: float):
        if "state" in st:
            self.status.state = str(st.get("state", self.status.state))
        if "target_pct" in st:
            v = st.get("target_pct", 0.0)
            self.status.target_pct = float(v or 0.0)
        if "rev" in st:
            self.status.rev = bool(st.get("rev", False))
        if "reason" in st:
            self.status.reason = str(st.get("reason", self.status.reason))
        if "available" in st:
            self.status.available = bool(st.get("available", self.status.available))
        if "stale" in st:
            self.status.stale = bool(st.get("stale", self.status.stale))
        self.status.last_t = now

    async def _handle_remote(self, method: str, params: dict):
        now = time.monotonic()
        if method == "drukmix_ping":
            await self._respond("command", "DrukMix driver: ping OK")
            return
        if method == "drukmix_status":
            await self._respond(
                "command",
                f"DrukMix driver: state={self.status.state} target={self.status.target_pct:.1f}% rev={int(self.status.rev)} available={int(self.status.available)} stale={int(self.status.stale)} reason={self.status.reason}",
            )
            return
        if method == "drukmix_stop":
            self.flush_until = 0.0
            self.backend.stop()
            await self._respond("error", "DrukMix driver: STOP")
            return
        if method == "drukmix_flush":
            pct = max(0.0, min(100.0, float(params.get("pct", 100.0))))
            dur = max(0.0, float(params.get("duration", 0.0)))
            self.flush_pct = pct
            self.flush_rev = False
            self.flush_until = (now + dur) if dur > 0 else 0.0
            self.backend.set_auto_target_pct(pct, False)
            await self._respond(
                "command", f"DrukMix driver: FLUSH {pct:.1f}% for {dur:.1f}s"
            )
            return
        if method == "drukmix_reset_fault":
            try:
                self.backend.reset_fault()
            except Exception as e:
                self.log.warning(f"reset_fault failed: {e}")
            await self._respond("command", "DrukMix driver: reset_fault sent")
            return

    async def _respond(self, level: str, msg: str):
        if not self.cfg.ui_notify:
            return
        try:
            await self.mr.respond(level, msg)
        except Exception:
            pass

    async def _loop(self):
        backoff = 0.5
        while True:
            try:
                await self._tick()
                backoff = 0.5
            except Exception as e:
                self.log.error(f"driver loop error: {e}")
                try:
                    self.backend.stop()
                except Exception:
                    pass
                try:
                    if self.mr:
                        await self.mr.close()
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 10.0)

    async def _tick(self):
        now = time.monotonic()

        # Drain notifications
        for _ in range(500):
            msg = self.mr.notify_nowait()
            if not msg:
                break
            if msg.get("method") == "notify_status_update":
                params = msg.get("params", [])
                if params and isinstance(params[0], dict):
                    st0 = params[0].get("drukmix_controller")
                    if isinstance(st0, dict):
                        self._apply_controller_status(st0, now)
                continue
            if msg.get("method") == "notify_remote_method":
                params = msg.get("params", [])
                if params and isinstance(params[0], str):
                    rmethod = params[0]
                    rparams = (
                        params[1]
                        if len(params) > 1 and isinstance(params[1], dict)
                        else {}
                    )
                    await self._handle_remote(rmethod, rparams)
                continue

        # Flush timeout
        if self.flush_until > 0.0 and now >= self.flush_until:
            self.flush_until = 0.0
            self.flush_pct = 0.0
            self.backend.stop()

        # Apply controller status (unless flushing)
        if self.flush_until <= 0.0:
            age = now - self.status.last_t
            stale = (age > max(0.1, self.cfg.status_timeout_s)) or self.status.stale
            blocked = (
                (not self.status.available) or stale or self.status.state == "blocked"
            )
            if self.cfg.debug_log and (now - self._last_debug_t) >= max(
                0.2, self.cfg.debug_log_period_s
            ):
                self._last_debug_t = now
                self.log.info(
                    "driver tick: state=%s target_pct=%.2f rev=%d available=%d stale=%d age=%.3f blocked=%d reason=%s",
                    self.status.state,
                    float(self.status.target_pct),
                    int(self.status.rev),
                    int(self.status.available),
                    int(stale),
                    age,
                    int(blocked),
                    self.status.reason,
                )
            if blocked:
                self.backend.stop()
            else:
                pct = max(0.0, min(100.0, float(self.status.target_pct)))
                rev = bool(self.status.rev)
                self.backend.set_auto_target_pct(pct, rev)

        await asyncio.sleep(1.0 / max(0.5, self.cfg.update_hz))


async def run_driver(cfg_path: str):
    cfg = load_cfg(cfg_path)
    if not cfg.enabled:
        return
    log = setup_logger(cfg.log_file, cfg.log_level)
    drv = Driver(cfg, log)
    await drv.start()


def main():
    cfg_path = os.environ.get("DRUKMIX_CONFIG", DEFAULT_CFG_PATH)
    asyncio.run(run_driver(cfg_path))


if __name__ == "__main__":
    main()
