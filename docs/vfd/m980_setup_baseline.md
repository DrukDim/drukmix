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

## Current gap

The repository still does not contain a short canonical checklist of:

- exactly which M980 parameters must be changed from factory defaults
- exactly which terminal/control-source settings are mandatory for the current field setup
- exactly which stop/ramp parameters are recommended for concrete printing

Those values should be extracted from the references and confirmed on real hardware before being presented here as project truth.
