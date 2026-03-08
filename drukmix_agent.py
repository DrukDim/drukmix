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

from agent.runtime.transport import (
    PROTO,
    USB_SET_FLOW,
    USB_SET_MAXLPM,
    USB_BRIDGE_STATUS,
    FLAG_REV,
    FLAG_STOP,
    FLAG_AUTO,
    crc16_ccitt_false,
    cobs_encode,
    cobs_decode,
    build_usb_packet,
    clamp,
    parse_bridge_status,
    BridgeSerial,
)

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
