from __future__ import annotations
import struct
import time
from typing import Any, Dict, Optional

import serial

from agent_config import clamp

PROTO = 1
USB_SET_FLOW = 1
USB_PING = 2
USB_SET_MAXLPM = 3
USB_RESET_FAULT = 4
USB_BRIDGE_STATUS = 101

FLAG_REV = 0x01
FLAG_STOP = 0x02
FLAG_AUTO = 0x04


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
        "proto": proto,
        "resp_type": msg_type,
        "resp_seq": seq,
        "mono_ms": mono_ms,
        "pump_link": int(pump_link),
        "age_ms": age_ms,
        "last_seen_div10": last_seen_div10,
        "last_ack_seq": last_ack_seq,
        "code": int(applied_code),
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
