from __future__ import annotations

class BridgeClient:
    def __init__(self, port: str, baudrate: int = 921600) -> None:
        self.port = port
        self.baudrate = baudrate

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def ping(self) -> dict:
        return {"ok": False, "reason": "not_implemented"}

    def set_flow(self, milli_lpm: int, flags: int) -> dict:
        return {"ok": False, "reason": "not_implemented", "milli_lpm": milli_lpm, "flags": flags}

    def set_max_lpm(self, milli_lpm: int) -> dict:
        return {"ok": False, "reason": "not_implemented", "milli_lpm": milli_lpm}
