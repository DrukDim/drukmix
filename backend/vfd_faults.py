from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VfdFaultInfo:
    code: int
    display: str
    name: str
    possible_causes: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)
    auto_reset_once: bool = False
    pause_print: bool = True
    severity: str = "fault"
    note: str = ""


VFD_FAULTS: dict[int, VfdFaultInfo] = {
    1: VfdFaultInfo(1, "Err01", "Inverter Unit Protection",
        ["The output circuit is grounded or short circuited",
         "The connecting cable of the motor is too long",
         "The module overheats",
         "The internal connections become loose",
         "The main control board is faulty",
         "The drive board is faulty",
         "The inverter module is faulty"],
        ["Eliminate external faults",
         "Install a reactor or an output filter",
         "Check the air filter and the cooling fan",
         "Connect all cables properly",
         "Contact for technical support",
         "Contact for technical support",
         "Contact for technical support"]),

    2: VfdFaultInfo(2, "Err02", "Overcurrent During Acceleration",
        ["The output circuit is grounded or short circuited",
         "The control method is vector and no parameter identification",
         "The acceleration time is too short",
         "Manual torque boost or V/F curve is not appropriate",
         "The voltage is too low",
         "The startup operation is performed on the rotating motor",
         "A sudden load is added during acceleration",
         "The inverter model is of too small power class"],
        ["Eliminate external faults",
         "Perform the motor auto-tuning",
         "Increase the acceleration time",
         "Adjust the manual torque boost or V/F curve",
         "Adjust the voltage to normal range",
         "Select rotational speed tracking restart or start the motor after it stops",
         "Remove the added load",
         "Select higher power rating inverter"]),

    3: VfdFaultInfo(3, "Err03", "Overcurrent During Deceleration",
        ["The output circuit is grounded or short circuited",
         "The control method is vector and no parameter identification",
         "The deceleration time is too short",
         "The voltage is too low",
         "A sudden load is added during deceleration",
         "The braking unit and braking resistor are not installed"],
        ["Eliminate external faults",
         "Perform the motor auto-tuning",
         "Increase the deceleration time",
         "Adjust the voltage to normal range",
         "Remove the added load",
         "Install the braking unit and braking resistor"]),

    4: VfdFaultInfo(4, "Err04", "Overcurrent at Constant Speed",
        ["The output circuit is grounded or short circuited",
         "The control method is vector and no parameter identification",
         "The voltage is too low",
         "A sudden load is added during deceleration",
         "The inverter model is of too small power class"],
        ["Eliminate external faults",
         "Perform the motor auto-tuning",
         "Adjust the voltage to normal range",
         "Remove the added load",
         "Select higher power rating inverter"]),

    5: VfdFaultInfo(5, "Err05", "Overvoltage During Acceleration",
        ["The input voltage is too high",
         "An external force drives the motor during acceleration",
         "The acceleration time is too short",
         "The braking unit and braking resistor are not installed"],
        ["Adjust the voltage to normal range",
         "Cancel the external force or install a braking resistor",
         "Increase the acceleration time",
         "Install the braking unit and braking resistor"]),

    6: VfdFaultInfo(6, "Err06", "Overvoltage During Deceleration",
        ["The input voltage is too high",
         "An external force drives the motor during deceleration",
         "The deceleration time is too short",
         "The braking unit and braking resistor are not installed"],
        ["Adjust the voltage to normal range",
         "Cancel the external force or install a braking resistor",
         "Increase the deceleration time",
         "Install the braking unit and braking resistor"]),

    7: VfdFaultInfo(7, "Err07", "Overvoltage at Constant Speed",
        ["The input voltage is too high",
         "An external force drives the motor during running"],
        ["Adjust the voltage to normal range",
         "Cancel the external force or install a braking resistor"]),

    8: VfdFaultInfo(8, "Err08", "Control Power Supply Fault",
        ["The input voltage is not within the allowable range"],
        ["Adjust the voltage to normal range"]),

    9: VfdFaultInfo(9, "Err09", "Undervoltage",
        ["Instantaneous power failure",
         "The inverter input voltage is not within the allowable range",
         "The DC bus voltage is abnormal",
         "The rectifier bridge and buffer resistor are faulty",
         "The drive board is faulty",
         "The main control board is faulty"],
        ["Reset the fault",
         "Adjust the voltage to normal range",
         "Contact for technical support",
         "Contact for technical support",
         "Contact for technical support",
         "Contact for technical support"]),

    10: VfdFaultInfo(10, "Err10", "Inverter Overload",
        ["The load is too heavy or locked rotor occurs on the motor",
         "The inverter model is of too small power class"],
        ["Reduce the load and check the motor and mechanical condition",
         "Select an inverter of higher power class"]),

    11: VfdFaultInfo(11, "Err11", "Motor Overload",
        ["P9-01 is set improperly",
         "The load is too heavy or locked rotor occurs on the motor",
         "The inverter model is of too small power class"],
        ["Set P9-01 correctly",
         "Reduce the load and check the motor and mechanical condition",
         "Select higher power rating inverter"]),

    12: VfdFaultInfo(12, "Err12", "Power Input Phase Loss",
        ["The three-phase power input is abnormal",
         "The drive board is faulty",
         "The lightening board is faulty",
         "The main control board is faulty"],
        ["Eliminate external faults",
         "Contact for technical support",
         "Contact for technical support",
         "Contact for technical support"]),

    13: VfdFaultInfo(13, "Err13", "Power Output Phase Loss",
        ["The cable connecting the inverter and the motor is faulty",
         "The inverter three-phase outputs are unbalanced when the motor is running",
         "The drive board is faulty",
         "The module is faulty"],
        ["Eliminate external faults",
         "Check whether the motor three-phase winding is normal",
         "Contact for technical support",
         "Contact for technical support"]),

    14: VfdFaultInfo(14, "Err14", "Module Overheat",
        ["The ambient temperature is too high",
         "The air filter is blocked",
         "The fan is damaged",
         "The thermally sensitive resistor of the module is damaged",
         "The inverter module is damaged"],
        ["Lower the ambient temperature",
         "Clean the air filter",
         "Replace the damaged fan",
         "Replace the damaged thermally sensitive resistor",
         "Replace the inverter module"]),

    15: VfdFaultInfo(15, "Err15", "External Equipment Fault",
        ["External fault signal is input via DI",
         "External fault signal is input via virtual I/O"],
        ["Reset the operation",
         "Reset the operation"]),

    16: VfdFaultInfo(16, "Err16", "Communication Fault",
        ["The controller is in abnormal state",
         "The communication cable is faulty",
         "The communication parameters are set improperly"],
        ["Check the cabling of host computer",
         "Check the communication cabling",
         "Set the communication parameters properly"],
        auto_reset_once=True,
        pause_print=True,
        severity="fault",
        note="safe one-shot startup reset"),

    17: VfdFaultInfo(17, "Err17", "Contactor Fault",
        ["The drive board and power supply are faulty",
         "The contactor is faulty"],
        ["Replace the faulty drive board or power supply board",
         "Replace the faulty contactor"]),

    18: VfdFaultInfo(18, "Err18", "Current Detection Fault",
        ["The HALL device is faulty",
         "The drive board is faulty"],
        ["Replace the faulty HALL device",
         "Replace the faulty drive board"]),

    19: VfdFaultInfo(19, "Err19", "Motor Auto-tuning Fault",
        ["The motor parameters are not set according to the nameplate",
         "The motor auto-tuning times out"],
        ["Set the motor parameters according to the nameplate properly",
         "Check the cable connecting the inverter and the motor"],
        auto_reset_once=False,
        pause_print=False,
        severity="warn"),

    21: VfdFaultInfo(21, "Err21", "EEPROM Write Fault",
        ["The EEPROM chip is damaged"],
        ["Replace the main control board"]),

    22: VfdFaultInfo(22, "Err22", "Inverter Hardware Fault",
        ["Overvoltage", "Overcurrent"],
        ["Solve as overvoltage fault", "Solve as overcurrent fault"]),

    23: VfdFaultInfo(23, "Err23", "Short Circuit to Ground",
        ["The motor is short circuited to the ground"],
        ["Replace the cable or motor"]),

    26: VfdFaultInfo(26, "Err26", "Accumulative Running Time Reached",
        ["The accumulative running time reaches the setting value"],
        ["Clear the record through the parameter initialization function"],
        auto_reset_once=False,
        pause_print=False,
        severity="info"),

    29: VfdFaultInfo(29, "Err29", "Accumulative Power-on Time Reached",
        ["The accumulative power-on time reaches the setting value"],
        ["Clear the record through the parameter initialization function"],
        auto_reset_once=False,
        pause_print=False,
        severity="info"),

    40: VfdFaultInfo(40, "Err40", "Pulse-by-pulse Current Limit Fault",
        ["The load is too heavy or locked rotor occurs on the motor",
         "The inverter model is of too small power class"],
        ["Reduce the load and check the motor and mechanical condition",
         "Select an inverter of higher power class"]),

    41: VfdFaultInfo(41, "Err41", "Motor Switchover Fault During Running",
        ["Change the selection of the motor via terminal during running of the inverter"],
        ["Perform motor switchover after the inverter stops"]),

    42: VfdFaultInfo(42, "Err42", "Excessive Speed Deviation Fault",
        ["Excessive speed deviation inspection parameter P6-10, P6-11 setting is not correct",
         "No parameter identification"],
        ["Correctly set parameter P6-10, P6-11",
         "Execute parameter identification"]),

    52: VfdFaultInfo(52, "A52", "Water Shortage Alarm",
        ["Pressure sensor is damaged",
         "The parameters of the inverter are incorrectly set",
         "The pipe network and motor are not correct"],
        ["Check pressure sensor",
         "Check inverter parameter setting",
         "Check motor and pipe"],
        auto_reset_once=False,
        pause_print=False,
        severity="alarm"),

    53: VfdFaultInfo(53, "Err53", "Overpressure Fault",
        ["Pressure sensor is damaged",
         "The parameters of the inverter are incorrectly set"],
        ["Check the pressure sensor",
         "Test whether inverter F5-18 is correctly set"]),

    56: VfdFaultInfo(56, "Err56", "Knitting Machine DI Fault",
        ["DI terminal function setting is not correct",
         "DI terminal is constantly high or low during the signal judgment cycle"],
        ["Check the DI terminal settings",
         "Check the status of the corresponding DI terminal"],
        auto_reset_once=False,
        pause_print=False,
        severity="warn"),

    64: VfdFaultInfo(64, "Err64", "Internal Communications Fault",
        ["Inverter internal communication failure"],
        ["Contact for technical support"]),

    65: VfdFaultInfo(65, "Err65", "Power Board Communication Fault",
        ["Power board abnormality"],
        ["Contact for technical support"]),
}


def get_vfd_fault_info(code: int) -> VfdFaultInfo | None:
    return VFD_FAULTS.get(int(code))


def format_vfd_fault(code: int) -> str:
    info = get_vfd_fault_info(code)
    if info is None:
        return f"Err{int(code):02d}"
    return f"{info.display} {info.name}"
