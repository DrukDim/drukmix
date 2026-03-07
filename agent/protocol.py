from __future__ import annotations
import struct

PROTO = 1

USB_SET_FLOW = 1
USB_PING = 2
USB_SET_MAXLPM = 3
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
            raise ValueError("COBS decode: zero code")
        i += 1

        end = i + code - 1
        if end > n:
            raise ValueError("COBS decode: truncated frame")

        out.extend(data[i:end])
        i = end

        if code != 0xFF and i < n:
            out.append(0)

    return bytes(out)

def pack_usb_header(msg_type: int, seq: int, mono_ms: int) -> bytes:
    return struct.pack("<BBHI", PROTO, msg_type, seq, mono_ms & 0xFFFFFFFF)

def build_frame(msg_type: int, seq: int, mono_ms: int, body: bytes) -> bytes:
    payload = pack_usb_header(msg_type, seq, mono_ms) + body
    crc = crc16_ccitt_false(payload)
    raw = payload + struct.pack("<H", crc)
    return cobs_encode(raw) + b"\x00"
