from __future__ import annotations
import struct
import time
from typing import Optional

import serial

from protocol import (
    USB_PING,
    USB_SET_FLOW,
    USB_SET_MAXLPM,
    USB_RESET_FAULT,
    USB_BRIDGE_STATUS,
    build_frame,
    cobs_decode,
    crc16_ccitt_false,
)

class BridgeClient:
    def __init__(self, port: str, baudrate: int = 921600, timeout: float = 0.5) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._seq = 0

    def open(self) -> None:
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

    def close(self) -> None:
        if self._ser:
            self._ser.close()
            self._ser = None

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        if self._seq == 0:
            self._seq = 1
        return self._seq

    def _mono_ms(self) -> int:
        return int(time.monotonic() * 1000)

    def _read_frame(self) -> bytes:
        if not self._ser:
            raise RuntimeError("serial not open")

        buf = bytearray()
        deadline = time.monotonic() + self.timeout

        while True:
            b = self._ser.read(1)
            if b:
                if b == b"\x00":
                    if not buf:
                        continue
                    return bytes(buf)
                buf.extend(b)
                continue

            if time.monotonic() >= deadline:
                raise TimeoutError("bridge read timeout")

    def _request(self, msg_type: int, body: bytes) -> dict:
        if not self._ser:
            raise RuntimeError("serial not open")

        self._ser.reset_input_buffer()

        seq = self._next_seq()
        frame = build_frame(msg_type, seq, self._mono_ms(), body)
        self._ser.write(frame)

        deadline = time.monotonic() + self.timeout
        last_valid_status = None

        while time.monotonic() < deadline:
            raw_cobs = self._read_frame()
            try:
                raw = cobs_decode(raw_cobs)
            except ValueError:
                continue

            if len(raw) < 8 + 2:
                continue

            got_crc = struct.unpack_from("<H", raw, len(raw) - 2)[0]
            calc_crc = crc16_ccitt_false(raw[:-2])
            if got_crc != calc_crc:
                continue

            proto, resp_type, resp_seq, mono_ms = struct.unpack_from("<BBHI", raw, 0)
            body = raw[8:-2]

            if resp_type != USB_BRIDGE_STATUS:
                continue

            if len(body) < 32:
                continue

            off = 0
            pump_link = body[off]; off += 1
            last_seen_div10, last_ack_seq = struct.unpack_from("<HH", body, off); off += 4
            applied_code = body[off]; off += 1
            err_flags, retry_count, send_fail_count = struct.unpack_from("<HHH", body, off); off += 6
            pump_max_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4

            pump_state, pump_fault_code = struct.unpack_from("<HH", body, off); off += 4
            pump_online = body[off]; off += 1
            pump_running = body[off]; off += 1
            target_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4
            actual_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4
            hw_setpoint_raw = struct.unpack_from("<i", body, off)[0]; off += 4
            pump_flags = struct.unpack_from("<H", body, off)[0]; off += 2

            status = {
                "ok": True,
                "proto": proto,
                "resp_type": resp_type,
                "resp_seq": resp_seq,
                "mono_ms": mono_ms,
                "pump_link": bool(pump_link),
                "last_seen_div10": last_seen_div10,
                "last_ack_seq": last_ack_seq,
                "applied_code": applied_code,
                "err_flags": err_flags,
                "retry_count": retry_count,
                "send_fail_count": send_fail_count,
                "pump_max_milli_lpm": pump_max_milli_lpm,

                "pump_state": pump_state,
                "pump_fault_code": pump_fault_code,
                "pump_online": bool(pump_online),
                "pump_running": bool(pump_running),
                "target_milli_lpm": target_milli_lpm,
                "actual_milli_lpm": actual_milli_lpm,
                "hw_setpoint_raw": hw_setpoint_raw,
                "pump_flags": pump_flags,
            }

            if resp_seq == seq:
                return status

            if resp_seq == 0:
                last_valid_status = status

        if last_valid_status is not None:
            return last_valid_status

        raise TimeoutError("no valid bridge response")

    def ping(self) -> dict:
        return self._request(USB_PING, b"")

    def set_flow(self, milli_lpm: int, flags: int) -> dict:
        body = struct.pack("<iB", int(milli_lpm), int(flags) & 0xFF)
        return self._request(USB_SET_FLOW, body)

    def set_max_lpm(self, milli_lpm: int) -> dict:
        body = struct.pack("<i", int(milli_lpm))
        return self._request(USB_SET_MAXLPM, body)

    def reset_fault(self, selector: int = 0) -> dict:
        body = struct.pack("<H", int(selector) & 0xFFFF)
        return self._request(USB_RESET_FAULT, body)
