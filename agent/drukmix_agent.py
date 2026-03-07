from __future__ import annotations
from bridge_client import BridgeClient
from pump_client import PumpClient

def main() -> None:
    bridge = BridgeClient("/dev/ttyACM0", 921600)
    pump = PumpClient(bridge)
    print("DrukMixAgent bootstrap")
    print(pump.stop())

if __name__ == "__main__":
    main()
