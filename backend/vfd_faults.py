from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VfdFaultInfo:
    code: int
    display: str
    name: str
    auto_reset_once: bool
    pause_print: bool
    severity: str
    note: str = ""


VFD_FAULTS: dict[int, VfdFaultInfo] = {
    1:  VfdFaultInfo(1,  "Err01", "Inverter Unit Protection", False, True,  "fault"),
    2:  VfdFaultInfo(2,  "Err02", "Overcurrent During Acceleration", False, True, "fault"),
    3:  VfdFaultInfo(3,  "Err03", "Overcurrent During Deceleration", False, True, "fault"),
    4:  VfdFaultInfo(4,  "Err04", "Overcurrent at Constant Speed", False, True, "fault"),
    5:  VfdFaultInfo(5,  "Err05", "Overvoltage During Acceleration", False, True, "fault"),
    6:  VfdFaultInfo(6,  "Err06", "Overvoltage During Deceleration", False, True, "fault"),
    7:  VfdFaultInfo(7,  "Err07", "Overvoltage at Constant Speed", False, True, "fault"),
    8:  VfdFaultInfo(8,  "Err08", "Control Power Supply Fault", False, True, "fault"),
    9:  VfdFaultInfo(9,  "Err09", "Undervoltage", False, True, "fault"),
    10: VfdFaultInfo(10, "Err10", "Inverter Overload", False, True, "fault"),
    11: VfdFaultInfo(11, "Err11", "Motor Overload", False, True, "fault"),
    12: VfdFaultInfo(12, "Err12", "Power Input Phase Loss", False, True, "fault"),
    13: VfdFaultInfo(13, "Err13", "Power Output Phase Loss", False, True, "fault"),
    14: VfdFaultInfo(14, "Err14", "Module Overheat", False, True, "fault"),
    15: VfdFaultInfo(15, "Err15", "External Equipment Fault", False, True, "fault"),
    16: VfdFaultInfo(16, "Err16", "Communication Fault", True,  True, "fault", "safe one-shot startup reset"),
    17: VfdFaultInfo(17, "Err17", "Contactor Fault", False, True, "fault"),
    18: VfdFaultInfo(18, "Err18", "Current Detection Fault", False, True, "fault"),
    19: VfdFaultInfo(19, "Err19", "Motor Auto-tuning Fault", False, False, "warn"),
    21: VfdFaultInfo(21, "Err21", "EEPROM Write Fault", False, True, "fault"),
    22: VfdFaultInfo(22, "Err22", "Inverter Hardware Fault", False, True, "fault"),
    23: VfdFaultInfo(23, "Err23", "Short Circuit to Ground", False, True, "fault"),
    26: VfdFaultInfo(26, "Err26", "Accumulative Running Time Reached", False, False, "info"),
    29: VfdFaultInfo(29, "Err29", "Accumulative Power-on Time Reached", False, False, "info"),
    40: VfdFaultInfo(40, "Err40", "Pulse-by-pulse Current Limit Fault", False, True, "fault"),
    41: VfdFaultInfo(41, "Err41", "Motor Switchover Fault During Running", False, True, "fault"),
    42: VfdFaultInfo(42, "Err42", "Excessive Speed Deviation Fault", False, True, "fault"),
    52: VfdFaultInfo(52, "A52",   "Water Shortage Alarm", False, False, "alarm"),
    53: VfdFaultInfo(53, "Err53", "Overpressure Fault", False, True, "fault"),
    56: VfdFaultInfo(56, "Err56", "Knitting Machine DI Fault", False, False, "warn"),
    64: VfdFaultInfo(64, "Err64", "Internal Communications Fault", False, True, "fault"),
    65: VfdFaultInfo(65, "Err65", "Power Board Communication Fault", False, True, "fault"),
}


def get_vfd_fault_info(code: int) -> VfdFaultInfo | None:
    return VFD_FAULTS.get(int(code))


def format_vfd_fault(code: int) -> str:
    info = get_vfd_fault_info(code)
    if info is None:
        return f"Err{int(code):02d}"
    return f"{info.display} {info.name}"
