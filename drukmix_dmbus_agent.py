#!/usr/bin/env python3
import asyncio
import os
import time
import fcntl
import logging
from logging.handlers import RotatingFileHandler

from agent_config import load_config
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
    backoff = 0.5

    while True:
        try:
            mr = MoonrakerClient(cfg.moonraker_ws, cfg)
            await mr.connect()
            log.info("drukmix_dmbus: connected to moonraker")

            while True:
                msg = mr.notify_nowait()
                if msg is None:
                    await asyncio.sleep(0.05)
                    continue

        except Exception as e:
            log.error(f"drukmix_dmbus: error: {e}")
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
