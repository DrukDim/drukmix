#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path


def api_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read().decode())


def api_post(base: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def print_state(base: str) -> str:
    j = api_get(base, "/printer/objects/query?print_stats")
    return j["result"]["status"]["print_stats"]["state"]


def wait_state(base: str, target: str, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if print_state(base) == target:
            return True
        time.sleep(0.5)
    return False


def run_one(base: str, repo_dir: str, filename: str, duration_s: float, run_s: float, idx: int) -> dict:
    st = print_state(base)
    if st == "printing":
        try:
            api_post(base, "/printer/print/cancel", {})
        except Exception:
            pass
        wait_state(base, "cancelled", 25)

    bridge_log = Path("/tmp/drukmix_fake_bridge.jsonl")
    bridge_log.write_text("")

    out_json = Path(f"/tmp/drukmix_probe_lead_report_run{idx}.json")
    cmd = [
        f"{repo_dir}/.venv/bin/python",
        f"{repo_dir}/tools/lab/measure_probe_lead.py",
        "--moonraker",
        base,
        "--bridge-log",
        str(bridge_log),
        "--out-json",
        str(out_json),
        "--duration-s",
        str(duration_s),
        "--poll-s",
        "0.10",
    ]
    p = subprocess.Popen(cmd, cwd=repo_dir)
    time.sleep(2.0)

    api_post(base, "/printer/print/start", {"filename": filename})
    time.sleep(run_s)
    try:
        api_post(base, "/printer/print/cancel", {})
    except Exception:
        pass

    p.wait(timeout=duration_s + 25)
    rep = json.loads(out_json.read_text())
    lead = rep.get("lead", {})
    cap = rep.get("capture", {})
    return {
        "run": idx,
        "observed_s": lead.get("observed_s"),
        "target_s": lead.get("target_s"),
        "error_s": lead.get("error_s"),
        "flow_events_positive": cap.get("flow_events_positive"),
        "flow_events_total": cap.get("flow_events_total"),
        "report_json": str(out_json),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moonraker", default="http://127.0.0.1:7125")
    ap.add_argument("--repo-dir", default="/home/debian/work/drukmix")
    ap.add_argument("--filename", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--duration-s", type=float, default=90.0)
    ap.add_argument("--run-s", type=float, default=30.0)
    ap.add_argument("--out-json", default="/tmp/drukmix_probe_lead_summary_3runs.json")
    args = ap.parse_args()

    results = []
    for i in range(1, args.runs + 1):
        r = run_one(args.moonraker, args.repo_dir, args.filename, args.duration_s, args.run_s, i)
        results.append(r)
        print(
            f"run={i} observed={r['observed_s']} target={r['target_s']} "
            f"error={r['error_s']} positive={r['flow_events_positive']}"
        )

    vals = [r["error_s"] for r in results if isinstance(r["error_s"], (int, float))]
    obs = [r["observed_s"] for r in results if isinstance(r["observed_s"], (int, float))]
    summary = {
        "runs": results,
        "n_valid": len(vals),
        "error_mean": (sum(vals) / len(vals)) if vals else None,
        "error_min": min(vals) if vals else None,
        "error_max": max(vals) if vals else None,
        "observed_mean": (sum(obs) / len(obs)) if obs else None,
    }
    Path(args.out_json).write_text(json.dumps(summary, indent=2))
    print(f"summary_json={args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
