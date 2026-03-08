from __future__ import annotations
import asyncio
import time


async def maybe_respond(mr, ui_notify: bool, last_state_msg_t: float, level: str, msg: str, min_interval_s: float = 0.4):
    if not ui_notify:
        return last_state_msg_t
    now = time.monotonic()
    if now - last_state_msg_t < min_interval_s:
        return last_state_msg_t
    try:
        await mr.respond(level, msg)
    except Exception:
        pass
    return now


async def pause_with_popup(mr, ks, pause_reason: str | None, reason: str, ui_notify: bool, last_state_msg_t: float):
    if ks.is_paused:
        return pause_reason, last_state_msg_t
    if pause_reason == reason:
        return pause_reason, last_state_msg_t
    pause_reason = reason
    try:
        await mr.pause_print()
    except Exception:
        pass
    last_state_msg_t = await maybe_respond(mr, ui_notify, last_state_msg_t, "error", reason, min_interval_s=0.0)
    return pause_reason, last_state_msg_t


async def burst_send(bridge, lpm: float, flags: int, burst_count: int, burst_interval_ms: int):
    count = max(1, int(burst_count))
    interval = max(0.0, float(burst_interval_ms)) / 1000.0
    for _ in range(count):
        try:
            bridge.send_flow(lpm, flags)
        except Exception:
            pass
        if interval > 0:
            await asyncio.sleep(interval)


async def confirm_applied(status_event, ls, want_code: int, stop: bool, timeout_s: float, tolerance_code: int):
    deadline = time.monotonic() + max(0.05, timeout_s)
    tol = max(0, min(int(tolerance_code), 50))
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
