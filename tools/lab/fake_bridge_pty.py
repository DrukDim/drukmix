#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pty
import select
import struct
import sys
import time
from dataclasses import dataclass, asdict

BRIDGE_PROTO = 1

USB_SET_FLOW = 1
USB_PING = 2
USB_SET_MAXLPM = 3
USB_RESET_FAULT = 4
USB_BRIDGE_STATUS = 101

PUMP_FLAG_RUNNING = 1 << 0
PUMP_FLAG_FORWARD = 1 << 1
PUMP_FLAG_REVERSE = 1 << 2
PUMP_FLAG_MANUAL_MODE = 1 << 3
PUMP_FLAG_REMOTE_MODE = 1 << 4
PUMP_FLAG_FAULT_LATCHED = 1 << 5
PUMP_FLAG_WDOG_STOP = 1 << 6
PUMP_FLAG_HW_READY = 1 << 7

MODE_AUTO = "AUTO"
MODE_MANUAL = "MANUAL"
MODE_UNKNOWN = "UNKNOWN"


@dataclass
class PumpModel:
    pump_max_milli_lpm: int = 10000
    target_milli_lpm: int = 0
    applied_milli_lpm: float = 0.0
    rev: bool = False
    mode: str = MODE_AUTO
    link_ok: bool = True
    fault_code: int = 0
    err_flags: int = 0
    retry_count: int = 0
    send_fail_count: int = 0
    applied_code: int = 0
    last_ack_seq: int = 0
    last_seen_mono_s: float = 0.0


class FakeBridgePTY:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.model = PumpModel(
            pump_max_milli_lpm=max(1000, int(args.max_lpm * 1000.0)),
            mode=args.mode,
            link_ok=not args.start_offline,
            fault_code=max(0, int(args.fault_code)),
        )
        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_path = os.ttyname(self.slave_fd)
        os.set_blocking(self.master_fd, False)
        self.rxbuf = bytearray()
        self.last_tick = time.monotonic()
        self.log_fp = open(args.log_jsonl, "a", encoding="utf-8") if args.log_jsonl else None

        if self.args.write_tty_path:
            with open(self.args.write_tty_path, "w", encoding="utf-8") as f:
                f.write(self.slave_path + "\n")

    def close(self):
        if self.log_fp:
            self.log_fp.close()
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        try:
            os.close(self.slave_fd)
        except OSError:
            pass

    def _log(self, event: str, **data):
        row = {
            "ts_mono": time.monotonic(),
            "event": event,
            **data,
        }
        if self.log_fp:
            self.log_fp.write(json.dumps(row, ensure_ascii=True) + "\n")
            self.log_fp.flush()
        if self.args.verbose:
            print(json.dumps(row, ensure_ascii=True), flush=True)

    def _tick(self):
        now = time.monotonic()
        dt = max(0.0, now - self.last_tick)
        self.last_tick = now

        target = float(self.model.target_milli_lpm)
        applied = float(self.model.applied_milli_lpm)

        if target >= applied:
            tau = max(1e-6, float(self.args.tau_up_s))
        else:
            tau = max(1e-6, float(self.args.tau_down_s))

        alpha = 1.0 - pow(2.718281828459045, -dt / tau)
        self.model.applied_milli_lpm = applied + (target - applied) * alpha

    def _flags(self) -> int:
        flags = PUMP_FLAG_HW_READY

        running_threshold = max(0.0, float(self.args.running_threshold_pct)) / 100.0
        running = self.model.applied_milli_lpm >= (running_threshold * self.model.pump_max_milli_lpm)
        if running:
            flags |= PUMP_FLAG_RUNNING

        if self.model.rev:
            flags |= PUMP_FLAG_REVERSE
        elif self.model.target_milli_lpm > 0:
            flags |= PUMP_FLAG_FORWARD

        if self.model.mode == MODE_MANUAL:
            flags |= PUMP_FLAG_MANUAL_MODE
        elif self.model.mode == MODE_AUTO:
            flags |= PUMP_FLAG_REMOTE_MODE

        if self.model.fault_code > 0:
            flags |= PUMP_FLAG_FAULT_LATCHED

        if not self.model.link_ok:
            flags |= PUMP_FLAG_WDOG_STOP

        return flags

    def _status_body(self) -> bytes:
        now = time.monotonic()
        age_ms = max(0, int((now - self.model.last_seen_mono_s) * 1000.0))
        last_seen_div10 = min(0xFFFF, age_ms // 10)

        pump_state = 2 if self.model.fault_code > 0 else 1
        running_threshold = max(0.0, float(self.args.running_threshold_pct)) / 100.0
        is_running = self.model.applied_milli_lpm >= (running_threshold * self.model.pump_max_milli_lpm)

        return struct.pack(
            "<BHHBHHHiHHBBiiiH",
            1 if self.model.link_ok else 0,
            last_seen_div10,
            self.model.last_ack_seq & 0xFFFF,
            self.model.applied_code & 0xFF,
            self.model.err_flags & 0xFFFF,
            self.model.retry_count & 0xFFFF,
            self.model.send_fail_count & 0xFFFF,
            int(self.model.pump_max_milli_lpm),
            pump_state & 0xFFFF,
            int(self.model.fault_code) & 0xFFFF,
            1 if self.model.link_ok else 0,
            1 if is_running else 0,
            int(self.model.target_milli_lpm),
            int(self.model.applied_milli_lpm),
            int(self.model.applied_milli_lpm),
            self._flags() & 0xFFFF,
        )

    def run(self):
        print(self.slave_path, flush=True)
        self._log("start", slave_path=self.slave_path, model=asdict(self.model))

        try:
            while True:
                self._tick()

                rlist, _, _ = select.select([self.master_fd], [], [], 0.05)
                if not rlist:
                    continue

                chunk = os.read(self.master_fd, 4096)
                if not chunk:
                    continue
                self.rxbuf.extend(chunk)

                while b"\x00" in self.rxbuf:
                    raw, _, rest = self.rxbuf.partition(b"\x00")
                    self.rxbuf = bytearray(rest)
                    if not raw:
                        continue

                    try:
                        dec = cobs_decode(bytes(raw))
                    except Exception as e:
                        self._log("decode_error", error=str(e))
                        continue

                    if len(dec) < 10:
                        self._log("short_packet", length=len(dec))
                        continue

                    frame = dec[:-2]
                    got_crc = struct.unpack_from("<H", dec, len(dec) - 2)[0]
                    calc_crc = crc16_ccitt_false(frame)
                    if got_crc != calc_crc:
                        self._log("crc_mismatch", got=got_crc, expected=calc_crc)
                        continue

                    self._handle_frame(frame)
        finally:
            self.close()

    def _send_status(self, seq_reply: int):
        hdr = struct.pack(
            "<BBHI",
            BRIDGE_PROTO,
            USB_BRIDGE_STATUS,
            int(seq_reply) & 0xFFFF,
            int(time.monotonic() * 1000.0) & 0xFFFFFFFF,
        )
        frame = hdr + self._status_body()
        crc = crc16_ccitt_false(frame)
        payload = cobs_encode(frame + struct.pack("<H", crc)) + b"\x00"
        os.write(self.master_fd, payload)

    def _handle_frame(self, frame: bytes):
        proto, pkt_type, seq, mono_ms = struct.unpack_from("<BBHI", frame, 0)
        body = frame[8:]

        if proto != BRIDGE_PROTO:
            self._log("bad_proto", proto=proto)
            return

        self.model.last_ack_seq = int(seq)
        self.model.last_seen_mono_s = time.monotonic()

        if pkt_type == USB_PING:
            self.model.applied_code = 0
            self._send_status(seq)
            self._log("ping", seq=seq)
            return

        if pkt_type == USB_SET_MAXLPM:
            if len(body) >= 4:
                self.model.pump_max_milli_lpm = max(1000, int(struct.unpack_from("<i", body, 0)[0]))
                self.model.applied_code = 0
                self._log("set_maxlpm", seq=seq, pump_max_milli_lpm=self.model.pump_max_milli_lpm)
            else:
                self.model.applied_code = 2
                self._log("set_maxlpm_bad_body", seq=seq, body_len=len(body))
            self._send_status(seq)
            return

        if pkt_type == USB_RESET_FAULT:
            self.model.fault_code = 0
            self.model.applied_code = 0
            self._log("reset_fault", seq=seq)
            self._send_status(seq)
            return

        if pkt_type == USB_SET_FLOW:
            if len(body) >= 5:
                target_milli_lpm, flags = struct.unpack_from("<iB", body, 0)
                self.model.target_milli_lpm = max(0, min(int(target_milli_lpm), self.model.pump_max_milli_lpm))
                self.model.rev = bool(flags & 0x01)
                self.model.applied_code = 0
                self._log(
                    "set_flow",
                    seq=seq,
                    target_milli_lpm=self.model.target_milli_lpm,
                    rev=self.model.rev,
                    mode=self.model.mode,
                    link_ok=self.model.link_ok,
                )
            else:
                self.model.applied_code = 2
                self._log("set_flow_bad_body", seq=seq, body_len=len(body))
            self._send_status(seq)
            return

        self.model.applied_code = 2
        self._log("unknown_packet", pkt_type=pkt_type, seq=seq, body_len=len(body), mono_ms=mono_ms)
        self._send_status(seq)


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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fake DrukMix bridge emulator over PTY")
    p.add_argument("--mode", choices=[MODE_AUTO, MODE_MANUAL, MODE_UNKNOWN], default=MODE_AUTO)
    p.add_argument("--start-offline", action="store_true", help="Start with link_ok=false")
    p.add_argument("--fault-code", type=int, default=0, help="Initial fault code")
    p.add_argument("--max-lpm", type=float, default=10.0, help="Pump max LPM")
    p.add_argument("--tau-up-s", type=float, default=1.0, help="Rise time constant in seconds")
    p.add_argument("--tau-down-s", type=float, default=0.8, help="Fall time constant in seconds")
    p.add_argument("--running-threshold-pct", type=float, default=2.0, help="Applied pct threshold for running")
    p.add_argument("--log-jsonl", default="", help="Optional JSONL log file path")
    p.add_argument("--write-tty-path", default="", help="Write PTY slave path to file")
    p.add_argument("--verbose", action="store_true", help="Print JSON events to stdout")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    emu = FakeBridgePTY(args)
    emu.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
