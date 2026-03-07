from __future__ import annotations
from bridge_client import BridgeClient

FLAG_REV  = 0x01
FLAG_STOP = 0x02
FLAG_AUTO = 0x04

class PumpClient:
    def __init__(self, bridge: BridgeClient) -> None:
        self.bridge = bridge

    def set_flow_lpm(self, lpm: float, reverse: bool = False, auto: bool = True) -> dict:
        milli_lpm = int(round(lpm * 1000.0))
        flags = 0
        if reverse:
            flags |= FLAG_REV
        if auto:
            flags |= FLAG_AUTO
        if milli_lpm <= 0:
            flags |= FLAG_STOP
        return self.bridge.set_flow(milli_lpm, flags)

    def stop(self) -> dict:
        return self.bridge.set_flow(0, FLAG_STOP)

    def set_max_lpm(self, lpm: float) -> dict:
        milli_lpm = int(round(lpm * 1000.0))
        return self.bridge.set_max_lpm(milli_lpm)
