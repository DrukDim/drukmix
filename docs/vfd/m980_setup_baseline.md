# M980 Setup Baseline

## Scope

This file captures the minimum M980-side setup assumptions required by the current `pump_vfd` path.

It is not intended to replace the vendor references.
It is intended to give DrukMix a short canonical baseline for what must be true on the VFD side before host control can work.

## Required control mode

The VFD must be configured for communication control over RS485 / Modbus RTU.

Current shared project rule:

- `F0-00 = 2` -> communication control

Source:
- [m900_m980_shared_semantics.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_m980_shared_semantics.md)

## Required communication assumptions

Current firmware assumptions:

- Modbus RTU over RS485
- baud rate: `9600`
- UART format: `8N1`
- slave address: `1`

Source:
- [pump_vfd_config.h](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd/src/pump_vfd_config.h)

## Status registers expected by current firmware

The current `pump_vfd` path expects monitor/state information compatible with:

- `1000H` -> running state
- `1001H` -> fault code
- `1003H` -> running frequency
- `1004H` -> running speed
- `1006H` -> output current

Source:
- [m900_m980_shared_semantics.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_m980_shared_semantics.md)

## Important runtime rule

Even when communication works, DrukMix must not treat `running == true` as proof that the motor is physically rotating.

Current logic must still separate:

- logical run state
- actual output frequency
- output current
- active fault code

Source:
- [m900_m980_shared_semantics.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_m980_shared_semantics.md)
- [modbus_driver_contract.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/modbus_driver_contract.md)

## Vendor references

Long-form vendor or field-reference material:

- [m980_mdriver_vfd_manual.pdf](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_mdriver_vfd_manual.pdf)
- [m900_mdriver_vfd_manual.pdf](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_mdriver_vfd_manual.pdf)

Short repository checklists:

- [m980_commissioning_checklist.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_commissioning_checklist.md)
- [m980_local_remote_modes.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_local_remote_modes.md)

## Current gap

The repository still does not contain a short canonical checklist of:

- exactly which stop/ramp parameters are recommended for concrete printing
- exact field-approved AI1 scaling / potentiometer wiring details
- exact field-approved local/remote switch wiring

Those values should be extracted from the references and confirmed on real hardware before being presented here as project truth.
