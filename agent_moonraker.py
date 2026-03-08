from __future__ import annotations
import asyncio
import json
from typing import Any, Dict, Optional

import websockets


class MoonrakerClient:
    def __init__(self, ws_url: str, cfg):
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
