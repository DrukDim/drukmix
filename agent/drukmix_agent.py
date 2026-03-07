from __future__ import annotations
import argparse
import json

from bridge_client import BridgeClient
from pump_client import PumpClient

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=921600)

    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")

    s_flow = sub.add_parser("set-flow")
    s_flow.add_argument("lpm", type=float)
    s_flow.add_argument("--reverse", action="store_true")
    s_flow.add_argument("--manual", action="store_true")

    s_max = sub.add_parser("set-max")
    s_max.add_argument("lpm", type=float)

    sub.add_parser("stop")

    args = ap.parse_args()

    bridge = BridgeClient(args.port, args.baud)
    pump = PumpClient(bridge)

    bridge.open()
    try:
        if args.cmd == "ping":
            result = bridge.ping()
        elif args.cmd == "set-flow":
            result = pump.set_flow_lpm(args.lpm, reverse=args.reverse, auto=not args.manual)
        elif args.cmd == "set-max":
            result = pump.set_max_lpm(args.lpm)
        elif args.cmd == "stop":
            result = pump.stop()
        else:
            raise RuntimeError(f"unknown command {args.cmd}")

        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        bridge.close()

if __name__ == "__main__":
    main()
