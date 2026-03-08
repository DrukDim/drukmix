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

Canonical `PumpStatus` contains only backend-independent runtime fields:
- `StatusCommon c`
- `target_milli_lpm`
- `actual_milli_lpm`
- `max_milli_lpm`
- `hw_setpoint_raw`
- `link_flags`
- `pump_flags`

Versioned duplicates such as `PumpStatusV1`, `PumpStatusV2`, etc. should not be introduced unless there is a hard compatibility requirement.

The status model must remain suitable for more than one backend. It must not become permanently VFD-specific.

It must not contain backend-only telemetry such as:
- VFD frequency
- VFD motor speed
- VFD output current

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

## Canonical pump command semantics

The canonical host-visible pump command behavior is:

### `PUMP_SET_FLOW`
Purpose:
- request a pump flow target in `milli_lpm`

Rules:
- `target_milli_lpm > 0` means normal remote pumping request
- `target_milli_lpm <= 0` is not the preferred hard-stop command; it may be treated as a stop-equivalent by a backend, but host orchestration should prefer explicit stop semantics
- command acceptance must depend on current node state, hardware readiness, and local/manual override state
- backend-specific low-level actuation is private to the node

ACK expectations:
- `ACK_OK` when the command is accepted for execution
- `ACK_ERROR` when the command is rejected due to local/manual mode, hardware not ready, invalid parameter, or backend failure
- `detail` should carry backend-specific reason when useful

### `PUMP_SET_MAX_FLOW`
Purpose:
- configure the current maximum allowed pump flow envelope for the active backend

Rules:
- this is a configuration/control bound, not a direct run command
- it must be backend-independent at the interface level even if internal implementation differs

### `OP_STOP`
Purpose:
- explicit unconditional remote-controlled stop request

Rules:
- this is the canonical stop command
- host-side print logic should prefer `OP_STOP` over overloading `PUMP_SET_FLOW=0`
- node must apply the safest supported stop behavior for the backend
- stop behavior may be ramp stop, controlled stop, or immediate safe stop depending on hardware/backend policy

### `OP_RESET_FAULT`
Purpose:
- request fault reset when the backend supports it

Rules:
- acceptance depends on backend capability and current state
- unsupported backends should reject with normalized ACK semantics

## Manual / local override semantics

Manual or local override must be treated as a first-class control condition.

### Required behavior
If manual/local mode is active:
- remote flow/run commands must not be executed as normal run commands
- node must report rejection through ACK
- status must clearly show manual/local condition
- host layer must treat the pump as not remotely controllable until manual/local mode clears

### ACK behavior under manual/local override
Recommended normalized behavior:
- `status = ACK_ERROR`
- `err_code = ERR_BAD_STATE` or a dedicated future normalized code if added later
- `detail = backend-specific reason`
- pump fault/status model may also expose `FAULT_PUMP_MANUAL_MODE` where appropriate

### Status behavior under manual/local override
Manual/local state must be visible through the canonical status model using flags rather than backend-specific transport hacks:
- `PUMP_FLAG_MANUAL_MODE`
- `PUMP_FLAG_REMOTE_MODE`

Only one control authority should be considered active at a time.

## Layer responsibility matrix

### Pump node responsibilities
The pump node is responsible for:
- backend I/O
- hardware state validation
- manual/local input evaluation
- safe command application
- generation of canonical ACK
- generation of canonical `PumpStatus`

The pump node is not responsible for:
- print orchestration
- flush planning
- long host-side state machines
- UI policy

### Bridge responsibilities
The bridge is responsible for:
- host transport termination
- ESP-NOW forwarding
- retry / timeout handling
- exposing bridge-visible status to the host

The bridge is not responsible for:
- print business logic
- backend-specific pump policy
- flush or prime sequencing
- interpreting print intent

### Agent responsibilities
The agent is responsible for:
- print-linked pump orchestration
- synchronization with Klipper state
- flush / prime sequencing
- unconditional stop policy
- minimum-flow cutoff policy
- watchdog policy above transport level
- exposing a clean model to Moonraker / Mainsail

## Agent state machine goals

The host-side agent should evolve toward a small explicit state machine.

Suggested high-level states:
- `DISCONNECTED`
- `IDLE`
- `ARMED`
- `RUNNING`
- `FLUSHING`
- `STOPPING`
- `FAULT`
- `MANUAL_LOCKOUT`

Required transitions should cover:
- print start / print stop
- commanded flow becoming positive
- commanded flow dropping below minimum threshold
- manual/local override appearing or clearing
- communication loss
- backend fault
- unconditional emergency stop

The agent should become the only place where print-time business logic is coordinated.

## Immediate next milestone

The next design focus should be:
1. finalize minimal canonical pump semantics shared by VFD and TPL backends
2. define host-side state machine for print-linked pump control
3. integrate that model with Klipper, Moonraker, and Mainsail

The project should now prioritize system behavior over further transport-layer complexity.

## Minimal shared pump runtime model

The minimal shared runtime model must work for both:
- VFD / Modbus pump backend
- TPL / relay + analog backend

This means the canonical model must describe pump behavior, not driver internals.

### Canonical `PumpStatus` meaning

`PumpStatus` should represent only shared runtime state that higher layers need for orchestration.

Recommended shared fields:
- `StatusCommon c`
- `target_milli_lpm`
- `actual_milli_lpm`
- `max_milli_lpm`
- `hw_setpoint_raw`
- `link_flags`
- `pump_flags`

### Meaning of shared fields

- `target_milli_lpm` = commanded target flow from the remote control layer
- `actual_milli_lpm` = best available backend-independent estimate of real delivered flow
- `max_milli_lpm` = active configured upper limit
- `hw_setpoint_raw` = backend raw actuation value, exposed only as a generic debug/control field
- `link_flags` = communication and transport visibility flags
- `pump_flags` = logical runtime flags such as running, manual mode, remote mode, watchdog stop, hardware ready

### What belongs in `pump_flags`

`pump_flags` should carry shared logical conditions, for example:
- `PUMP_FLAG_RUNNING`
- `PUMP_FLAG_FORWARD`
- `PUMP_FLAG_REVERSE`
- `PUMP_FLAG_MANUAL_MODE`
- `PUMP_FLAG_REMOTE_MODE`
- `PUMP_FLAG_FAULT_LATCHED`
- `PUMP_FLAG_WDOG_STOP`
- `PUMP_FLAG_HW_READY`

### What does NOT belong in canonical `PumpStatus`

The canonical shared status should not directly depend on one backend family.

Examples that should not live in canonical `PumpStatus`:
- VFD output frequency
- VFD shaft speed
- VFD output current
- TPL-specific relay diagnostics
- TPL-specific potentiometer raw value
- backend-private hardware diagnostics

Those values may still exist, but they should be treated as backend diagnostics, not canonical pump state.

## Backend diagnostics rule

Backend-specific diagnostics are allowed, but they must be clearly separated from the shared control model.

Examples:
- VFD diagnostics:
  - actual frequency
  - motor speed
  - output current
  - raw drive fault register
- TPL diagnostics:
  - relay state
  - selector state
  - analog command value
  - backend-specific fault inputs

These diagnostics should not drive the project architecture.
They are secondary to the shared pump abstraction.

## Design consequence for next code changes

Before adding more fields or transport payloads, check them against this rule:

Question:
- does this field describe shared pump behavior needed by host orchestration?

If yes:
- it may belong in canonical `PumpStatus`

If no:
- it should stay backend-local or move into an optional diagnostics path later

## VFD architecture and docs

### Where to look first

- `docs/vfd/README.md` — index: what document to open and when
- `docs/vfd/m900_m980_shared_semantics.md` — shared semantics for M900/M980
- `docs/vfd/m900_m980_differences.md` — series differences and capability boundary
- `docs/vfd/m900_m980_faults.md` — baseline fault map and recovery policy
- `docs/vfd/modbus_driver_contract.md` — contract between `pump_vfd`, `bridge`, `agent`, and future Klipper integration
- `config/vfd_profiles.yaml` — per-series profiles/capabilities

### Project rules for VFD fault handling

- Only communication-loss class faults are candidates for automatic recovery.
- All other VFD faults must remain operator-visible and should pause/hold the print flow until investigated.
- Fault recovery policy should live on the ESP / `pump_vfd` side, not in an external host service.
- `running` must not be interpreted as proof of physical shaft motion when commanded frequency is zero.
- Shared transport/status logic may be reused across M900 and M980, but series differences must stay in profiles/capabilities.

### Current implementation direction

1. Keep common Modbus transport and status model.
2. Move comm-loss recovery to ESP-side logic.
3. Preserve operator-handled behavior for all non-communication faults.
4. Validate real run behavior using different target speeds and observed status registers before deeper Klipper integration.
