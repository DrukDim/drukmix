#!/usr/bin/env python3
import asyncio
import os
import time
import fcntl
import logging
from logging.handlers import RotatingFileHandler

from agent_config import load_config
from agent_transport import BridgeSerial
from agent_moonraker import MoonrakerClient


def setup_logger(log_file: str) -> logging.Logger:
    lg = logging.getLogger("drukmix_dmbus")
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


async def mr_respond(mr, msg: str, level: str = "command"):
    try:
        await mr.respond(level, msg)
    except Exception:
        pass


async def run_agent(cfg_path: str):
    cfg = load_config(cfg_path)
    log = setup_logger(cfg.log_file)

    lock_path = os.path.expanduser("~/printer_data/logs/drukmix_dmbus.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error("drukmix_dmbus: another instance is running")
        return

    mr = None
    bridge = None
    backoff = 0.5

    last_status = {}
    last_status_t = 0.0

    while True:
        try:
            cfg = load_config(cfg_path)

            bridge = BridgeSerial(cfg.serial_port, cfg.serial_baud)
            bridge.open()

            mr = MoonrakerClient(cfg.moonraker_ws, cfg)
            await mr.connect()

            for method_name in (
                "drukmix_dmbus_ping",
                "drukmix_dmbus_status",
            ):
                await mr.call("connection.register_remote_method", {"method_name": method_name})

            log.info("drukmix_dmbus: connected")

            while True:
                for st in bridge.read_status_frames():
                    last_status = st
                    last_status_t = time.monotonic()

                for _ in range(50):
                    msg = mr.notify_nowait()
                    if not msg:
                        break

                    method = msg.get("method")
                    if method == "drukmix_dmbus_ping":
                        await mr_respond(mr, "DrukMix DMBus: ping OK")
                        continue

                    if method == "drukmix_dmbus_status":
                        age = -1
                        if last_status_t > 0.0:
                            age = int((time.monotonic() - last_status_t) * 1000)

                        if last_status:
                            txt = (
                                "DrukMix DMBus: "
                                f"bridge_status=1 "
                                f"pump_link={int(last_status.get('pump_link', 0))} "
                                f"pump_online={int(last_status.get('pump_online', 0))} "
                                f"pump_running={int(last_status.get('pump_running', 0))} "
                                f"state={last_status.get('pump_state')} "
                                f"fault={last_status.get('pump_fault_code')} "
                                f"target={last_status.get('target_milli_lpm')} "
                                f"actual={last_status.get('actual_milli_lpm')} "
                                f"code={last_status.get('applied_code')} "
                                f"age_ms={age}"
                            )
                        else:
                            txt = "DrukMix DMBus: no bridge status yet"

                        await mr_respond(mr, txt)

                await asyncio.sleep(0.02)

        except Exception as e:
            log.error(f"drukmix_dmbus: error: {e}")
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
