# DrukMix

DrukMix is a control stack for a concrete 3D printing system built around Klipper, Moonraker, Mainsail, and external pump/mixer hardware.

The project goal is not a generic plastic FDM workflow. It is focused on a concrete extrusion machine with:
- screw-based extruder
- screw pump feeding material through a hose
- external pump driver hardware
- custom control logic integrated with print execution

## Project goals

The long-term goal is to build a stable and extensible control stack that can:
- synchronize pump flow with printing motion
- support multiple pump driver backends under one common model
- integrate with Klipper, Moonraker, and Mainsail
- support operational logic such as flush, prime, hard stop, minimum-flow cutoff, and fault handling
- remain version-pinned and modifiable without upstream updates breaking local changes

## Current architecture

The project is split into three main layers.

### 1. Pump node
An ESP-based hardware-side node located near the real pump driver.

Responsibilities:
- receive bus commands
- validate local operating conditions
- apply commands to the physical driver
- generate ACK frames
- generate STATUS frames

Non-responsibilities:
- print orchestration
- flush scheduling
- Klipper print policy
- UI logic

### 2. Bridge
A USB to ESP-NOW bridge.

Responsibilities:
- receive commands from the host
- forward them to the pump node
- track ACK timeout and retries
- expose bridge and pump status back to the host

The bridge should stay transport-oriented and should not accumulate print business logic.

### 3. Agent / host-side control
The host-side layer that will integrate with Klipper, Moonraker, and Mainsail.

Responsibilities:
- print-state integration
- flush / prime sequencing
- unconditional stop logic
- minimum-flow cutoff
- synchronization policy
- UI/state exposure to higher layers

## Canonical bus rules

### One abstract pump model
The system must expose one logical pump abstraction to upper layers.

Different hardware implementations may exist underneath:
- VFD / Modbus pump
- TPL / analog + relay pump
- future drivers

Upper layers should not care which pump driver is physically present.

### Canonical command set
Current canonical pump commands:
- `PUMP_SET_FLOW`
- `PUMP_SET_MAX_FLOW`
- `OP_STOP`
- `OP_RESET_FAULT`

Optional future commands:
- `PUMP_PRIME`
- `PUMP_FLUSH`

### Canonical ACK
There is one ACK format for pump commands:

    struct Ack {
      uint16_t ack_seq;
      uint8_t  status;
      uint8_t  reserved;
      uint16_t err_code;
      uint16_t detail;
    };

Semantics:
- `ack_seq` = acknowledged command sequence
- `status` = normalized result (`ACK_OK`, `ACK_ERROR`, `ACK_BUSY`, `ACK_UNSUPPORTED`)
- `err_code` = normalized system-level reason
- `detail` = backend-specific detail or raw driver error information

### Canonical pump status
There is one canonical runtime pump status type:
- `PumpStatus`

Versioned duplicates such as `PumpStatusV1`, `PumpStatusV2`, etc. should not be introduced unless there is a hard compatibility requirement.

The status model must remain suitable for more than one backend. It must not become permanently VFD-specific.

## Manual / local mode rule

Manual or local override is a core part of the system model.

If local/manual control is active:
- remote run commands must not be treated as normal run commands
- the node should report rejection through ACK
- the current manual/local state must be visible in status

This rule is required for:
- VFD-based pump control with a local selector/toggle
- future TPL/relay-based pump control with manual override inputs

## RS485 note

The current RS485 design uses shared `DE/RE` on one control pin.

This is acceptable for half-duplex operation as long as:
- TX mode is enabled before transmission
- the UART is flushed before switching back to RX
- turnaround timing is handled correctly

Shared `DE/RE` is not itself a blocker for receiving feedback from the VFD.

## Current direction

The project should avoid overgrowing the transport layer.

Target shape:
- one abstract pump model
- one ACK model
- one `PumpStatus` model
- bridge remains simple
- agent becomes the intelligent coordination layer

## What not to do

Do not:
- duplicate status structures without necessity
- move print business logic into the bridge
- let transport details dictate the whole architecture
- make the bus permanently specific to only one pump backend

## Immediate next milestone

The next design focus should be:
1. finalize minimal canonical pump semantics shared by VFD and TPL backends
2. define host-side state machine for print-linked pump control
3. integrate that model with Klipper, Moonraker, and Mainsail

The project should now prioritize system behavior over further transport-layer complexity.
