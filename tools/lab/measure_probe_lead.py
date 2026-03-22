#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


PLANNER_FIELDS = [
    "queue_tail_s",
    "print_window_active",
    "time_to_print_start_s",
    "time_to_print_stop_s",
    "control_velocity_mms",
]


@dataclass
class ProbeSample:
    eventtime: float
    queue_tail_s: Optional[float]
    print_window_active: bool
    time_to_print_start_s: Optional[float]
    time_to_print_stop_s: Optional[float]
    control_velocity_mms: Optional[float]


@dataclass
class FlowEvent:
    ts_mono: float
    target_milli_lpm: int
    rev: bool


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def query_probe(moonraker_http: str, timeout_s: float = 1.0) -> ProbeSample:
    payload = {
        "objects": {
            "drukmix_planner_probe": PLANNER_FIELDS,
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{moonraker_http.rstrip('/')}/printer/objects/query",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        out = json.loads(r.read().decode("utf-8"))

    result = out.get("result", {})
    eventtime = _safe_float(result.get("eventtime"))
    status = result.get("status", {})
    pp = status.get("drukmix_planner_probe", {}) if isinstance(status, dict) else {}

    if eventtime is None:
        raise RuntimeError("moonraker response missing result.eventtime")

    return ProbeSample(
        eventtime=eventtime,
        queue_tail_s=_safe_float(pp.get("queue_tail_s")),
        print_window_active=bool(pp.get("print_window_active", False)),
        time_to_print_start_s=_safe_float(pp.get("time_to_print_start_s")),
        time_to_print_stop_s=_safe_float(pp.get("time_to_print_stop_s")),
        control_velocity_mms=_safe_float(pp.get("control_velocity_mms")),
    )


def read_lookahead_from_cfg(cfg_path: str) -> float:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cp.read(cfg_path)
    if cp.has_section("drukmix"):
        v = cp.getfloat("drukmix", "pump_start_lookahead_s", fallback=4.0)
    else:
        v = 4.0
    return max(0.0, min(30.0, float(v)))


def parse_flow_events(bridge_log_path: str, start_mono: float) -> list[FlowEvent]:
    out: list[FlowEvent] = []
    if not os.path.exists(bridge_log_path):
        return out

    with open(bridge_log_path, "r", encoding="utf-8") as f:
        for line in f:
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

            tgt = row.get("target_milli_lpm")
            try:
                target = int(tgt)
            except Exception:
                continue

            out.append(FlowEvent(ts_mono=ts, target_milli_lpm=target, rev=bool(row.get("rev", False))))

    return out


def nearest_sample(samples: list[ProbeSample], ts_mono: float) -> Optional[ProbeSample]:
    if not samples:
        return None
    return min(samples, key=lambda s: abs(s.eventtime - ts_mono))


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure planner probe lead against fake bridge flow commands")
    ap.add_argument("--moonraker-http", default="http://127.0.0.1:7125")
    ap.add_argument("--cfg", default=os.path.expanduser("~/printer_data/config/drukmix.cfg"))
    ap.add_argument("--bridge-log", default="/tmp/drukmix_fake_bridge.jsonl")
    ap.add_argument("--duration-s", type=float, default=45.0)
    ap.add_argument("--poll-s", type=float, default=0.10)
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    duration_s = max(2.0, float(args.duration_s))
    poll_s = max(0.02, float(args.poll_s))
    lookahead_s = read_lookahead_from_cfg(args.cfg)

    start_mono = time.monotonic()
    end_mono = start_mono + duration_s

    samples: list[ProbeSample] = []
    errors = 0

    while time.monotonic() < end_mono:
        t0 = time.monotonic()
        try:
            sample = query_probe(args.moonraker_http)
            samples.append(sample)
        except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError):
            errors += 1

        dt = time.monotonic() - t0
        sleep_s = max(0.0, poll_s - dt)
        if sleep_s > 0:
            time.sleep(sleep_s)

    flow_events = parse_flow_events(args.bridge_log, start_mono)
    positive_flow = [e for e in flow_events if e.target_milli_lpm > 0]
    first_positive = positive_flow[0] if positive_flow else None

    first_prestart: Optional[ProbeSample] = None
    for s in samples:
        t = s.time_to_print_start_s
        if t is None:
            continue
        if 0.0 < t <= lookahead_s:
            first_prestart = s
            break

    measured = {
        "config": {
            "moonraker_http": args.moonraker_http,
            "cfg": args.cfg,
            "bridge_log": args.bridge_log,
            "duration_s": duration_s,
            "poll_s": poll_s,
            "pump_start_lookahead_s": lookahead_s,
        },
        "capture": {
            "start_mono": start_mono,
            "end_mono": end_mono,
            "samples": len(samples),
            "query_errors": errors,
            "flow_events_total": len(flow_events),
            "flow_events_positive": len(positive_flow),
        },
        "first_prestart": None,
        "first_positive_set_flow": None,
        "lead": {
            "observed_s": None,
            "target_s": lookahead_s,
            "error_s": None,
        },
    }

    if first_prestart is not None:
        measured["first_prestart"] = {
            "eventtime": first_prestart.eventtime,
            "time_to_print_start_s": first_prestart.time_to_print_start_s,
            "time_to_print_stop_s": first_prestart.time_to_print_stop_s,
            "queue_tail_s": first_prestart.queue_tail_s,
            "print_window_active": first_prestart.print_window_active,
            "control_velocity_mms": first_prestart.control_velocity_mms,
        }

    if first_positive is not None:
        near = nearest_sample(samples, first_positive.ts_mono)
        lead_obs = None
        if near is not None and near.time_to_print_start_s is not None:
            lead_obs = float(near.time_to_print_start_s)

        measured["first_positive_set_flow"] = {
            "ts_mono": first_positive.ts_mono,
            "target_milli_lpm": first_positive.target_milli_lpm,
            "rev": first_positive.rev,
            "nearest_probe_eventtime": None if near is None else near.eventtime,
            "nearest_probe_time_to_print_start_s": None if near is None else near.time_to_print_start_s,
            "nearest_probe_time_to_print_stop_s": None if near is None else near.time_to_print_stop_s,
        }

        if lead_obs is not None:
            measured["lead"]["observed_s"] = lead_obs
            measured["lead"]["error_s"] = lead_obs - lookahead_s

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(measured, f, ensure_ascii=True, indent=2)

    print(f"samples={measured['capture']['samples']} query_errors={measured['capture']['query_errors']}")
    print(f"flow_events_total={measured['capture']['flow_events_total']} positive={measured['capture']['flow_events_positive']}")

    if measured["first_prestart"] is None:
        print("first_prestart=none")
    else:
        fp = measured["first_prestart"]
        print(f"first_prestart_t_start={fp['time_to_print_start_s']}")

    if measured["first_positive_set_flow"] is None:
        print("first_positive_set_flow=none")
        print("lead_observed_s=none")
        print("hint=run a print/travel scenario that creates planner print window")
    else:
        fs = measured["first_positive_set_flow"]
        print(f"first_positive_set_flow_ts={fs['ts_mono']}")
        print(f"nearest_t_start_s={fs['nearest_probe_time_to_print_start_s']}")
        lead_obs = measured["lead"]["observed_s"]
        if lead_obs is None:
            print("lead_observed_s=none")
        else:
            print(f"lead_observed_s={lead_obs:.3f}")
            print(f"lead_target_s={lookahead_s:.3f}")
            print(f"lead_error_s={measured['lead']['error_s']:.3f}")

    if args.out_json:
        print(f"report_json={args.out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
