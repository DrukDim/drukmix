#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


QUERY_FIELDS = {
    "print_stats": ["state", "filename", "print_duration"],
    "drukmix_planner_probe": [
        "queue_tail_s",
        "print_window_active",
        "time_to_print_start_s",
        "time_to_print_stop_s",
        "control_velocity_mms",
    ],
    "virtual_sdcard": ["file_position", "progress", "is_active", "file_size"],
}


@dataclass
class Sample:
    ts_mono: float
    eventtime: float
    print_state: Optional[str]
    filename: Optional[str]
    print_duration: Optional[float]
    print_window_active: bool
    time_to_print_start_s: Optional[float]
    time_to_print_stop_s: Optional[float]
    queue_tail_s: Optional[float]
    control_velocity_mms: Optional[float]
    file_position: Optional[int]
    progress: Optional[float]
    sd_active: Optional[bool]


@dataclass
class FlowEvent:
    ts_mono: float
    target_milli_lpm: int
    rev: bool
    mode: Optional[str]


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def moonraker_query(base: str) -> Sample:
    payload = {"objects": QUERY_FIELDS}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/printer/objects/query",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        out = json.loads(resp.read().decode("utf-8"))

    result = out.get("result", {})
    status = result.get("status", {}) if isinstance(result, dict) else {}
    ps = status.get("print_stats", {}) if isinstance(status, dict) else {}
    pp = status.get("drukmix_planner_probe", {}) if isinstance(status, dict) else {}
    vs = status.get("virtual_sdcard", {}) if isinstance(status, dict) else {}

    eventtime = _safe_float(result.get("eventtime"))
    if eventtime is None:
        raise RuntimeError("moonraker response missing eventtime")

    return Sample(
        ts_mono=time.monotonic(),
        eventtime=eventtime,
        print_state=ps.get("state"),
        filename=ps.get("filename"),
        print_duration=_safe_float(ps.get("print_duration")),
        print_window_active=bool(pp.get("print_window_active", False)),
        time_to_print_start_s=_safe_float(pp.get("time_to_print_start_s")),
        time_to_print_stop_s=_safe_float(pp.get("time_to_print_stop_s")),
        queue_tail_s=_safe_float(pp.get("queue_tail_s")),
        control_velocity_mms=_safe_float(pp.get("control_velocity_mms")),
        file_position=_safe_int(vs.get("file_position")),
        progress=_safe_float(vs.get("progress")),
        sd_active=bool(vs.get("is_active")) if "is_active" in vs else None,
    )


def moonraker_post(base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_new_log(path: Path, start_size: int) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if start_size < 0 or start_size > len(data):
        start_size = 0
    return data[start_size:].decode("utf-8", "ignore")


def parse_bridge_events(path: Path, start_mono: float) -> list[FlowEvent]:
    out: list[FlowEvent] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("event") != "set_flow":
            continue
        ts = _safe_float(row.get("ts_mono"))
        if ts is None or ts < start_mono:
            continue
        tgt = _safe_int(row.get("target_milli_lpm"))
        if tgt is None:
            continue
        out.append(
            FlowEvent(
                ts_mono=ts,
                target_milli_lpm=tgt,
                rev=bool(row.get("rev", False)),
                mode=row.get("mode"),
            )
        )
    out.sort(key=lambda e: e.ts_mono)
    return out


def semantic_of(sample: Sample, prestart_s: float, prestop_s: float) -> str:
    t_start = sample.time_to_print_start_s
    t_stop = sample.time_to_print_stop_s
    if sample.print_window_active:
        if t_stop is not None and 0.0 <= t_stop <= prestop_s:
            return "prestop"
        return "print"
    if t_start is not None and 0.0 < t_start <= prestart_s:
        return "prestart"
    if sample.print_state == "printing":
        return "travel_gap"
    return "other"


def nearest_flow(events: list[FlowEvent], ts: float) -> Optional[FlowEvent]:
    if not events:
        return None
    return min(events, key=lambda e: abs(e.ts_mono - ts))


def to_plain(obj: Any) -> Any:
    if isinstance(obj, list):
        return [to_plain(x) for x in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit prestart/print/prestop transitions and pump-flow sync")
    ap.add_argument("--moonraker-http", default="http://127.0.0.1:7125")
    ap.add_argument("--bridge-log", default="/tmp/drukmix_fake_bridge.jsonl")
    ap.add_argument("--drukmix-log", default=str(Path("~/printer_data/logs/drukmix.log").expanduser()))
    ap.add_argument("--duration-s", type=float, default=300.0)
    ap.add_argument("--poll-s", type=float, default=0.10)
    ap.add_argument("--prestart-lookahead-s", type=float, default=4.0)
    ap.add_argument("--prestop-lookahead-s", type=float, default=3.0)
    ap.add_argument("--start-print-file", default="")
    ap.add_argument("--cancel-at-end", action="store_true")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    duration_s = max(5.0, float(args.duration_s))
    poll_s = max(0.02, float(args.poll_s))
    prestart_s = max(0.0, float(args.prestart_lookahead_s))
    prestop_s = max(0.0, float(args.prestop_lookahead_s))

    run_tag = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"/tmp/drukmix_sync_audit_{run_tag}")
    out_dir.mkdir(parents=True, exist_ok=True)

    bridge_path = Path(args.bridge_log)
    drukmix_log_path = Path(args.drukmix_log)
    log_start_size = drukmix_log_path.stat().st_size if drukmix_log_path.exists() else 0

    start_mono = time.monotonic()
    deadline = start_mono + duration_s

    if args.start_print_file:
        try:
            moonraker_post(args.moonraker_http, "/printer/print/cancel", {})
        except Exception:
            pass
        time.sleep(1.5)
        moonraker_post(
            args.moonraker_http,
            "/printer/print/start",
            {"filename": args.start_print_file},
        )

    samples: list[Sample] = []
    query_errors = 0

    while time.monotonic() < deadline:
        cycle_t0 = time.monotonic()
        try:
            samples.append(moonraker_query(args.moonraker_http))
        except Exception:
            query_errors += 1
        dt = time.monotonic() - cycle_t0
        if poll_s > dt:
            time.sleep(poll_s - dt)

    # Small flush delay so bridge and logs catch final writes.
    time.sleep(1.0)

    if args.cancel_at_end:
        try:
            moonraker_post(args.moonraker_http, "/printer/print/cancel", {})
        except Exception:
            pass

    bridge_events = parse_bridge_events(bridge_path, start_mono)
    drukmix_new = read_new_log(drukmix_log_path, log_start_size)

    semantic_samples = []
    for s in samples:
        semantic_samples.append({
            "sample": s,
            "semantic": semantic_of(s, prestart_s=prestart_s, prestop_s=prestop_s),
        })

    transition_points = []
    prev_sem = None
    for row in semantic_samples:
        cur = row["semantic"]
        if prev_sem is None:
            prev_sem = cur
            continue
        if cur != prev_sem:
            s = row["sample"]
            near = nearest_flow(bridge_events, s.ts_mono)
            transition_points.append(
                {
                    "to_semantic": cur,
                    "sample": s,
                    "nearest_set_flow": near,
                }
            )
        prev_sem = cur

    prestart_points = [x for x in transition_points if x["to_semantic"] == "prestart"]
    print_points = [x for x in transition_points if x["to_semantic"] == "print"]
    prestop_points = [x for x in transition_points if x["to_semantic"] == "prestop"]

    # Correlation and on/off consistency during print windows.
    active_pairs: list[tuple[float, float]] = []
    vel_pos_total = 0
    vel_pos_pump_on = 0
    vel_zeroish_total = 0
    vel_zeroish_pump_on = 0

    bridge_idx = 0
    last_target = 0.0
    for row in semantic_samples:
        s: Sample = row["sample"]
        while bridge_idx < len(bridge_events) and bridge_events[bridge_idx].ts_mono <= s.ts_mono:
            last_target = float(bridge_events[bridge_idx].target_milli_lpm)
            bridge_idx += 1

        if not s.print_window_active:
            continue
        if s.control_velocity_mms is None:
            continue

        v = float(s.control_velocity_mms)
        active_pairs.append((v, last_target))

        if v > 0.5:
            vel_pos_total += 1
            if last_target > 0:
                vel_pos_pump_on += 1
        else:
            vel_zeroish_total += 1
            if last_target > 0:
                vel_zeroish_pump_on += 1

    corr = None
    if len(active_pairs) >= 5:
        xs = [a for a, _ in active_pairs]
        ys = [b for _, b in active_pairs]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        if vx > 0 and vy > 0:
            cov = sum((x - mx) * (y - my) for x, y in active_pairs)
            corr = cov / math.sqrt(vx * vy)

    ratio_vel_pos = (vel_pos_pump_on / vel_pos_total) if vel_pos_total else None
    ratio_vel_zeroish = (vel_zeroish_pump_on / vel_zeroish_total) if vel_zeroish_total else None

    # Additional evidence from agent transitions log lines.
    semantic_log_lines = [
        ln for ln in drukmix_new.splitlines() if "drukmix transition:" in ln and "semantic=" in ln
    ]

    summary = {
        "capture": {
            "duration_s": duration_s,
            "poll_s": poll_s,
            "start_mono": start_mono,
            "samples": len(samples),
            "query_errors": query_errors,
            "bridge_set_flow_total": len(bridge_events),
        },
        "counts": {
            "prestart": len(prestart_points),
            "print": len(print_points),
            "prestop": len(prestop_points),
        },
        "sync": {
            "corr_velocity_vs_target_active_window": corr,
            "pump_on_ratio_when_velocity_positive": ratio_vel_pos,
            "pump_on_ratio_when_velocity_zeroish": ratio_vel_zeroish,
            "velocity_positive_samples": vel_pos_total,
            "velocity_zeroish_samples": vel_zeroish_total,
        },
        "evidence": {
            "prestart_points": [
                {
                    "to_semantic": p["to_semantic"],
                    "sample": p["sample"],
                    "nearest_set_flow": p["nearest_set_flow"],
                }
                for p in prestart_points[:100]
            ],
            "print_points": [
                {
                    "to_semantic": p["to_semantic"],
                    "sample": p["sample"],
                    "nearest_set_flow": p["nearest_set_flow"],
                }
                for p in print_points[:100]
            ],
            "prestop_points": [
                {
                    "to_semantic": p["to_semantic"],
                    "sample": p["sample"],
                    "nearest_set_flow": p["nearest_set_flow"],
                }
                for p in prestop_points[:100]
            ],
            "drukmix_transition_lines": semantic_log_lines[-200:],
            "last_bridge_set_flow": bridge_events[-80:],
        },
    }

    (out_dir / "samples.jsonl").write_text(
        "".join(json.dumps(to_plain(s), ensure_ascii=True) + "\n" for s in samples),
        encoding="utf-8",
    )
    (out_dir / "bridge_set_flow.jsonl").write_text(
        "".join(json.dumps(to_plain(e), ensure_ascii=True) + "\n" for e in bridge_events),
        encoding="utf-8",
    )
    (out_dir / "drukmix_new.log").write_text(drukmix_new, encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(to_plain(summary), ensure_ascii=True, indent=2), encoding="utf-8")

    print(json.dumps(to_plain(summary), ensure_ascii=True, indent=2))
    print(f"OUTDIR {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
