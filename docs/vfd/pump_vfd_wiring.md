# Pump VFD Wiring

## Scope

This file documents the currently known wiring assumptions for the `pump_vfd` node.

It is intentionally limited to facts that are already present in the repository or confirmed by current firmware configuration.

If a hardware detail is not confirmed, it should stay marked as `TODO` rather than being presented as settled truth.

## Current firmware pin map

The current `pump_vfd` firmware uses these MCU pins for VFD Modbus communication:

- `UART_RX_PIN = 16`
- `UART_TX_PIN = 17`
- `UART_RTS_PIN = 4`
- `UART_BAUD = 9600`
- UART format `8N1`
- `MODBUS_SLAVE_ID = 1`

Source:
- [pump_vfd_config.h](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd/src/pump_vfd_config.h)

## Current communication model

The control path is:

`ESP node -> RS485 transceiver -> Modbus RTU -> VFD`

Current project assumptions:

- RS485 / Modbus RTU is the control path for `pump_vfd`
- the VFD must be configured for communication control
- the host/bridge/driver stack should treat VFD state as Modbus-reported backend state, not as guaranteed physical truth

Source:
- [modbus_driver_contract.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/modbus_driver_contract.md)

## Direction signal

`UART_RTS_PIN = 4` is currently documented in firmware as:

- `RTS / DE-RE if used`

This means the current firmware expects a transceiver design where transmit/receive direction may be controlled externally from that pin.

What is still not fully documented in the repository:

- the exact RS485 transceiver module currently used
- whether `DE` and `RE` are tied together
- whether the board uses auto-direction hardware instead of explicit direction control

Until verified on hardware, those details must remain open.

## What must be physically documented

The following should be confirmed and then kept here explicitly:

- MCU board model used for `pump_vfd`
- RS485 transceiver model
- ESP pin to transceiver pin mapping:
  - TX
  - RX
  - DE
  - RE
- transceiver to VFD mapping:
  - `A`
  - `B`
  - `GND` if used
- whether common ground is required in the actual deployed wiring
- power rail used for the transceiver
- whether local decoupling capacitors are required and where they are placed

## Current gaps

The repository does **not** currently document:

- a canonical RS485 transceiver wiring diagram
- whether termination or biasing resistors are present in the deployed hardware
- whether local decoupling is required on the transceiver board
- whether the current field wiring uses shield/ground connection in a specific way

Those are real documentation gaps, not implementation details to guess.
