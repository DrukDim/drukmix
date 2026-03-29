# VFD Docs Index

This directory is the canonical documentation entrypoint for the current `pump_vfd` backend.

It covers:

- shared M900 / M980 semantics,
- current Modbus / RS485 driver assumptions,
- backend-local fault meaning,
- currently known wiring assumptions,
- vendor reference PDFs kept inside the repository.

## Read in this order

### 1. Backend baseline

- [modbus_driver_contract.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/modbus_driver_contract.md)
- [m900_m980_shared_semantics.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_m980_shared_semantics.md)

Read these first when:

- changing `pump_vfd` runtime behavior,
- changing host/bridge/pump ownership boundaries,
- changing status or fault interpretation,
- changing recovery policy.

### 2. Series differences

- [m900_m980_differences.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_m980_differences.md)

Read this when:

- adding or revising series-specific support,
- changing assumptions about IO or capability profiles,
- adding M900/M980-specific behavior.

### 3. Fault handling

- [m900_m980_faults.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_m980_faults.md)

Read this when:

- fault codes appear in runtime status,
- changing reset / recovery policy,
- deciding what may auto-recover and what must stay operator-visible.

### 4. Wiring and setup

- [pump_vfd_wiring.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/pump_vfd_wiring.md)
- [pump_vfd_debug.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/pump_vfd_debug.md)
- [m980_setup_baseline.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_setup_baseline.md)
- [m980_commissioning_checklist.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_commissioning_checklist.md)
- [m980_local_remote_modes.md](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_local_remote_modes.md)

Read these when:

- wiring ESP to RS485 / VFD,
- using and extending the standalone `pump_vfd_debug` firmware,
- checking MCU pin assignments,
- confirming the minimum M980-side configuration needed for communication control,
- commissioning a reset M980 from motor nameplate entry through autotune,
- wiring or reasoning about local-manual vs Modbus mode switching.

### 5. Vendor references

- [m980_mdriver_vfd_manual.pdf](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_mdriver_vfd_manual.pdf)
- [m900_mdriver_vfd_manual.pdf](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m900_mdriver_vfd_manual.pdf)

These PDFs are reference material, not canonical project truth by themselves.
Project rules should be extracted from them into short repository docs only after they are verified against real hardware behavior.

## Current project rules

1. One shared transport/state model for M900 and M980.
2. Series differences belong in capability/profile logic, not scattered runtime guesses.
3. `running` is not proof of physical shaft rotation.
4. Auto-recovery is currently limited to communication-loss style failures only.
5. All other process/device faults remain operator-visible unless a stricter verified policy replaces that rule.

## Known documentation gaps

The repository still needs clearer canonical documentation for:

- exact RS485 transceiver wiring used in field hardware,
- exact A/B/GND wiring to the VFD,
- whether current field hardware requires explicit transceiver decoupling or special bias/termination,
- exact M980 parameter checklist required from factory defaults for the current deployed path,
- exact field-approved DI terminal and wiring for local/remote switching.

## Related code

- [firmware/pump_vfd/](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd)
- [firmware/bridge/](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/bridge)
- [drukmix_driver.py](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/drukmix_driver.py)
