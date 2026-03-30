# Pump / Bridge V2 Contract

This file defines the proposed next-step architecture for `pump` nodes, `bridge`, and host-side integration.

It is not a VFD-only design.

The goal is:

- one backend-neutral runtime control model,
- one backend-neutral runtime status model,
- one optional backend-local service plane,
- one transport model that works over `ESP-NOW` without a router,
- no duplicate semantic layers between host, bridge, and pump nodes.

This file must be read together with:

- [ARCHITECTURE.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/ARCHITECTURE.md)
- [docs/vfd/pump_vfd_debug.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/pump_vfd_debug.md)

## Why This File Exists

The current codebase already contains a shared bus contract in:

- [firmware/drukmix_bus/include/drukmix_bus_v1.h](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/drukmix_bus/include/drukmix_bus_v1.h)

But the live system still has semantic duplication and loss:

- `pump_vfd` uses the shared bus over `ESP-NOW`,
- `bridge` translates that into a separate USB protocol,
- host-side Python re-derives mode/running semantics from partial bridge payloads,
- `pump_tpl` uses a different custom `ESP-NOW` protocol and does not yet participate in the same shared status model.

That creates multiple truths for the same machine state.

## Current Audited Gaps

### 1. `pump_vfd` still hides real mode truth

In:

- [firmware/pump_vfd/src/dmbus_pump_node.cpp](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd/src/dmbus_pump_node.cpp)

the function:

- `is_manual_mode_active_()`

is still a `TODO` and currently always returns `false`.

That means the node cannot yet publish the real physical `MANUAL/AUTO` mode we have now proven on hardware.

### 2. `pump_vfd` hardcodes mode as remote

In:

- [firmware/pump_vfd/src/dmbus_pump_link.cpp](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd/src/dmbus_pump_link.cpp)

the outgoing status frame always sets:

- `f.p.c.mode = dmbus::MODE_REMOTE`

This is no longer acceptable once physical manual/auto switching is part of the machine.

### 3. Bridge USB protocol is a second semantic model

In:

- [firmware/bridge/src/bridge_proto.h](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/bridge/src/bridge_proto.h)
- [firmware/bridge/src/usb_link.h](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/bridge/src/usb_link.h)
- [backend/bridge_usb_transport.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/backend/bridge_usb_transport.py)

the USB side exposes a different transport/status contract from the one already used over `ESP-NOW`.

That contract is too narrow for:

- real mode truth,
- backend-local telemetry,
- service operations such as register read/write or preset apply.

### 4. Actual telemetry is lost or misrepresented

In:

- [firmware/pump_vfd/src/dmbus_pump_node.cpp](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd/src/dmbus_pump_node.cpp)
- [backend/bridge_usb_transport.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/backend/bridge_usb_transport.py)

`actual_milli_lpm` is effectively unavailable for `VFD`, and the host bridge parser explicitly ignores the bridge-side `actual_milli_lpm` field.

This is correct in one sense:

- we must not fake measured flow.

But the architecture still needs a truthful place for backend-reported runtime telemetry such as:

- actual frequency,
- motor speed,
- current,
- DI state,
- backend mode detail.

### 5. `pump_tpl` is outside the shared pump-node contract

In:

- [firmware/pump_tpl/src/drivers/EspNowProto.h](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_tpl/src/drivers/EspNowProto.h)
- [firmware/pump_tpl/src/drivers/EspNowLink.cpp](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_tpl/src/drivers/EspNowLink.cpp)

`pump_tpl` uses a separate custom protocol and therefore cannot cleanly share:

- node enrollment,
- common status semantics,
- common `MANUAL/AUTO` rules,
- optional backend service operations.

### 6. Host backends already depend on mode truth

In:

- [backend/backend_pumpvfd.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/backend/backend_pumpvfd.py)
- [backend/backend_pumptpl.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/backend/backend_pumptpl.py)
- [drukmix_driver.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/drukmix_driver.py)

the host runtime already makes decisions from:

- `control_mode`
- `link_ok`
- `faulted`
- `running`

So the pump/bridge contract must expose this truth cleanly and consistently.

## Target Architecture

The target model has two planes.

### 1. Generic Runtime Control Plane

This plane is canonical for all pump backends.

It includes:

- node discovery / hello,
- capabilities,
- stop,
- reset fault,
- set automatic target,
- backend-normalized runtime status.

This is the only plane used by:

- `drukmix_controller`
- automatic printer synchronization
- normal host runtime orchestration

### 2. Backend Service Plane

This plane is optional and capability-gated.

It exists for:

- register reads,
- register writes,
- applying presets,
- reading backend snapshots,
- backend-specific diagnostics,
- commissioning and maintenance.

This plane must never be required for:

- normal automatic pumping,
- planner-driven synchronization,
- core safety gating.

For `pump_tpl`, some or all service operations may be unsupported.

For `pump_vfd`, the service plane is essential.

## Canonical Runtime Status Model

The shared runtime status model must carry truth, not guesses.

### Required generic fields

- `link_ok`
  - transport freshness truth
- `backend_online`
  - backend-device communication truth
- `state`
  - backend-reported normalized state
- `control_mode`
  - `AUTO`
  - `MANUAL`
  - `UNKNOWN`
- `running`
  - backend-reported delivered run state
- `rev_active`
  - direction truth if available
- `faulted`
  - normalized fault latch
- `fault_code`
  - backend fault code
- `target_milli_lpm`
  - backend-reported commanded target if meaningful
- `hw_setpoint_raw`
  - backend-reported raw commanded output
- `pump_flags`
  - backend capability/state flags
- `age_ms`
  - transport freshness age

### Rules

- `control_mode` is backend/device truth, not host guess.
- `MANUAL` must block automatic orchestration.
- `UNKNOWN` must block automatic orchestration.
- `running` is backend-reported delivered behavior, not requested target.
- `target_pct` remains host/orchestration truth and stays host-side.
- `actual_milli_lpm` must only exist if it is measured or defensibly backend-reported as actual material flow.

### VFD-specific runtime telemetry

For `pump_vfd`, the following are useful but must remain backend-local:

- `actual_freq_x10`
- `actual_speed_raw`
- `output_current_x10`
- `di_state`
- `run_state_raw`
- `backend_mode_line_active`

These must not be promoted into the generic runtime status model.

They belong in the service plane snapshot.

## Canonical Capability Model

`HELLO` / `GET_CAPS` should expose at least:

- `CAP_REMOTE_STOP`
- `CAP_SETPOINT_CONTROL`
- `CAP_TELEMETRY`
- `CAP_FAULT_RESET`
- `CAP_ACTUAL_FEEDBACK`
- `CAP_LOCAL_MANUAL_SENSE`

Additional new capability bits should be added for:

- `CAP_SERVICE_READ_PARAM`
- `CAP_SERVICE_WRITE_PARAM`
- `CAP_SERVICE_APPLY_PRESET`
- `CAP_SERVICE_BACKEND_SNAPSHOT`

These bits must be capability-gated per backend:

- `pump_vfd`: expected to support all service bits above
- `pump_tpl`: likely supports snapshot only, and maybe none of the parameter/preset bits

## Transport Model

### ESP-NOW

`ESP-NOW` remains the node-to-bridge transport.

Rules:

- no router required
- one enrolled peer set
- shared bus framing for all nodes
- one semantic contract for both `pump_vfd` and `pump_tpl`

### USB bridge

The bridge should stop defining its own semantic worldview.

Target rule:

- USB should carry the same bus semantics that the pump node already uses
- bridge should translate medium, not invent a second control model

That does not require byte-for-byte identical framing immediately, but it does require:

- no semantic loss,
- no bridge-side mode invention,
- no host-side mode reconstruction from partial fields.

## Proposed V2 Contract Direction

### Keep

- `HELLO`
- `HELLO_ACK`
- `MSG_CMD`
- `MSG_ACK`
- `MSG_STATUS`
- shared `StatusCommon`
- shared `PumpStatus`

### Fix

- `pump_vfd` must populate real `mode`
- `pump_vfd` must set `PUMP_FLAG_MANUAL_MODE` and `PUMP_FLAG_REMOTE_MODE` from real hardware truth
- `pump_tpl` must move onto the shared bus model
- bridge must expose the real `mode` and real `pump_flags` unchanged

### Add

A small service family, carried through the same node identity and routing model.

The service family should support:

- `SERVICE_GET_BACKEND_SNAPSHOT`
- `SERVICE_READ_PARAM`
- `SERVICE_WRITE_PARAM`
- `SERVICE_APPLY_PRESET`
- `SERVICE_LIST_PRESETS`

This can be expressed either as:

- new `PumpOpcode` values in the shared bus,
- or one service envelope opcode with backend-local payload.

The important rule is semantic, not syntactic:

- service operations are explicit,
- capability-gated,
- backend-local,
- and separate from normal runtime orchestration.

## Host Model

### What stays the same

The host orchestration loop remains:

- planner-driven
- backend-neutral
- based on `control_mode`, `fault`, `link_ok`, and planner demand

The current Python runtime already expects this separation in:

- [drukmix_driver.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/drukmix_driver.py)
- [klipper_extra/drukmix_controller.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/klipper_extra/drukmix_controller.py)

### What changes

The host should stop depending on a bridge-only status worldview.

Instead:

- the host backend reads one truthful generic status,
- and optional tooling can call backend service operations for diagnostics/configuration.

This means:

- automatic runtime does not need raw register reads,
- commissioning and service tooling can read/write parameters without inventing printer-specific hacks.

## Pump-VFD Specific Direction

`pump_vfd` should be rebuilt around a shared `M980` core extracted from the debug work.

That core should expose:

- runtime poll
- command write
- mode line read
- fault reset
- register read/write
- preset apply

Then:

- `pump_vfd` uses the generic runtime plane plus service plane
- `pump_vfd_debug` uses the same core but exposes HTTP tooling

This avoids two different VFD implementations drifting apart.

## Pump-TPL Specific Direction

`pump_tpl` must not be forced into a VFD worldview.

But it should still use the same shared node model:

- same `HELLO`
- same `ACK`
- same generic `PumpStatus`
- same `control_mode` semantics
- same `MANUAL/AUTO/UNKNOWN` safety rule

Backend-local service support may be minimal.

For `TPL`, examples of backend-local snapshot fields could be:

- `applied_code`
- `manual_any`
- `wiper_tpl_active`
- `dir_asserted`
- `dir_external_low`

## Performance and Stability Targets

### Modbus bring-up matrix

Evaluate only:

- `9600`
- `19200`
- `38400`

Per baud:

- 200 status reads
- 100 frequency writes
- 50 run/stop cycles
- 20 `AUTO/MANUAL` button cycles
- no `Err16`
- no CRC failures
- no read/write timeout

### Pump-node polling budget

Start with:

- status polling at `5 Hz`
- command writes at `<= 10 Hz`
- one outstanding Modbus transaction at a time

Do not mix:

- aggressive debug/service reads
- with normal operational polling

without explicit arbitration.

## Immediate Code Changes Required

### `pump_vfd`

- implement real `is_manual_mode_active_()`
- publish real `mode`
- publish real `pump_flags`
- stop hardcoding `MODE_REMOTE`
- stop lying by omission about backend mode
- add backend snapshot / register service support
- share `M980` core with `pump_vfd_debug`

### `pump_tpl`

- migrate off custom `EspNowProto`
- use the shared bus contract
- publish real `mode`
- publish truthful manual/auto state
- optionally expose backend snapshot service

### `bridge`

- stop being the owner of a second semantic protocol
- preserve node mode/status truth
- route service operations without reinterpreting them
- expose a host surface that is semantically aligned with the shared bus

### host Python

- keep generic backend status normalized in one place
- do not derive `control_mode` by guessing from incomplete bridge fields
- keep service operations outside the automatic control loop
- allow CLI/tooling access to backend service calls

## Practical Phasing

### Phase 1

- freeze the confirmed `M980` physical button/manual-auto truth
- implement real mode sensing in `pump_vfd`
- make host see truthful `AUTO/MANUAL/UNKNOWN`

### Phase 2

- add VFD backend snapshot service
- add register read/write service
- add preset apply service

### Phase 3

- migrate `pump_tpl` onto the same shared bus/runtime status model
- keep backend-local service support optional

### Phase 4

- replace or collapse the narrow bridge USB protocol so that no second semantic model remains

## Bottom Line

The next architecture should not be:

- more VFD-specific fields in the generic model,
- more bridge-local reinterpretation,
- or more host-side guessing.

It should be:

- one generic runtime pump contract,
- one optional backend service plane,
- one truthful mode model,
- one bridge that preserves semantics instead of redefining them,
- and one host runtime that stays planner-authoritative and backend-neutral.
