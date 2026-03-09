from __future__ import annotations

import struct
import time
from typing import Optional

import serial


BRIDGE_PROTO = 1

USB_SET_FLOW = 1
USB_PING = 2
USB_SET_MAXLPM = 3
USB_RESET_FAULT = 4
USB_BRIDGE_STATUS = 101


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    code_index = 0
    out.append(0)
    code = 1

    for b in data:
        if b == 0:
            out[code_index] = code
            code_index = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_index] = code
                code_index = len(out)
                out.append(0)
                code = 1

    out[code_index] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)

    while i < n:
        code = data[i]
        if code == 0:
            raise ValueError("invalid COBS code 0")
        i += 1
        end = i + code - 1
        if end > n:
            raise ValueError("truncated COBS packet")
        out.extend(data[i:end])
        i = end
        if code != 0xFF and i < n:
            out.append(0)

    return bytes(out)


class BridgeUsbTransport:
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.seq = 1
        self.rxbuf = bytearray()
        self._last_status: Optional[dict] = None

    def open(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.02)
        self.rxbuf.clear()

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None

    def _next_seq(self) -> int:
        v = self.seq
        self.seq = (self.seq + 1) & 0xFFFF
        if self.seq == 0:
            self.seq = 1
        return v

    def _send_packet(self, pkt_type: int, body: bytes = b""):
        if not self.ser:
            raise RuntimeError("serial not open")
        hdr = struct.pack(
            "<BBHI",
            BRIDGE_PROTO,
            pkt_type,
            self._next_seq(),
            int(time.monotonic() * 1000) & 0xFFFFFFFF,
        )
        frame = hdr + body
        crc = crc16_ccitt_false(frame)
        frame += struct.pack("<H", crc)
        enc = cobs_encode(frame) + b"\x00"
        self.ser.write(enc)
        self.ser.flush()

    def _poll_packet(self) -> Optional[bytes]:
        if not self.ser:
            return None

        while True:
            chunk = self.ser.read(256)
            if chunk:
                self.rxbuf.extend(chunk)

            if b"\x00" not in self.rxbuf:
                if not chunk:
                    return None
                continue

            raw, _, rest = self.rxbuf.partition(b"\x00")
            self.rxbuf = bytearray(rest)
            if not raw:
                continue

            try:
                dec = cobs_decode(bytes(raw))
            except Exception:
                continue

            if len(dec) < 10:
                continue

            got_crc = struct.unpack_from("<H", dec, len(dec) - 2)[0]
            calc_crc = crc16_ccitt_false(dec[:-2])
            if got_crc != calc_crc:
                continue

            return dec[:-2]

    def _parse_status(self, pkt: bytes) -> Optional[dict]:
        if len(pkt) < 8:
            return None

        proto, pkt_type, seq_reply, t_ms = struct.unpack_from("<BBHI", pkt, 0)
        if proto != BRIDGE_PROTO or pkt_type != USB_BRIDGE_STATUS:
            return None

        body = memoryview(pkt)[8:]
        if len(body) < 31:
            return None

        off = 0
        pump_link = bool(body[off]); off += 1
        last_seen_div10 = struct.unpack_from("<H", body, off)[0]; off += 2
        last_ack_seq = struct.unpack_from("<H", body, off)[0]; off += 2
        applied_code = body[off]; off += 1
        err_flags = struct.unpack_from("<H", body, off)[0]; off += 2
        retry_count = struct.unpack_from("<H", body, off)[0]; off += 2
        send_fail_count = struct.unpack_from("<H", body, off)[0]; off += 2
        pump_max_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4

        pump_state = struct.unpack_from("<H", body, off)[0]; off += 2
        pump_fault_code = struct.unpack_from("<H", body, off)[0]; off += 2
        pump_online = bool(body[off]); off += 1
        pump_running = bool(body[off]); off += 1
        target_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4
        actual_milli_lpm = struct.unpack_from("<i", body, off)[0]; off += 4
        hw_setpoint_raw = struct.unpack_from("<i", body, off)[0]; off += 4
        pump_flags = struct.unpack_from("<H", body, off)[0]; off += 2

        applied_pct = None
        if pump_max_milli_lpm > 0:
            applied_pct = max(0.0, min(100.0, (actual_milli_lpm * 100.0) / pump_max_milli_lpm))

        return {
            "link_ok": pump_link,
            "control_mode": "UNKNOWN",
            "running": pump_running,
            "rev_active": None,
            "faulted": pump_fault_code != 0,
            "fault_code": pump_fault_code,
            "applied_pct": applied_pct,
            "age_ms": int(last_seen_div10) * 10,
            "pump_state": pump_state,
            "pump_online": pump_online,
            "target_milli_lpm": target_milli_lpm,
            "actual_milli_lpm": actual_milli_lpm,
            "hw_setpoint_raw": hw_setpoint_raw,
            "pump_flags": pump_flags,
            "last_ack_seq": last_ack_seq,
            "applied_code": applied_code,
            "err_flags": err_flags,
            "retry_count": retry_count,
            "send_fail_count": send_fail_count,
            "pump_max_milli_lpm": pump_max_milli_lpm,
            "seq_reply": seq_reply,
            "bridge_t_ms": t_ms,
        }

    def _request_status(self) -> Optional[dict]:
        self._send_packet(USB_PING, b"")
        deadline = time.monotonic() + 0.30
        while time.monotonic() < deadline:
            pkt = self._poll_packet()
            if not pkt:
                continue
            st = self._parse_status(pkt)
            if st is not None:
                self._last_status = st
                return st
        return None

    def read_status(self):
        st = self._request_status()
        if st is not None:
            return st
        return self._last_status

    def vfd_set_run(self, pct: float, rev: bool):
        max_lpm = 10000
        target_milli_lpm = int(max(0.0, min(100.0, pct)) * max_lpm / 100.0)
        flags = 0x01 if rev else 0x00
        self._send_packet(USB_SET_FLOW, struct.pack("<iB", target_milli_lpm, flags))

    def vfd_stop(self):
        self._send_packet(USB_SET_FLOW, struct.pack("<iB", 0, 0))

    def vfd_reset_fault(self):
        self._send_packet(USB_RESET_FAULT, struct.pack("<H", 0))
