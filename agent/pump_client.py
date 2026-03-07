from __future__ import annotations
from bridge_client import BridgeClient

class PumpClient:
    def __init__(self, bridge: BridgeClient) -> None:
        self.bridge = bridge

    def set_flow_lpm(self, lpm: float, flags: int = 0) -> dict:
        milli_lpm = int(round(lpm * 1000.0))
        return self.bridge.set_flow(milli_lpm, flags)

    def stop(self) -> dict:
        return self.bridge.set_flow(0, 0x02)
