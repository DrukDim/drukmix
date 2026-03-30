# Pump VFD Debug

## Scope

This file is the canonical repository source of truth for `pump_vfd_debug`.

It exists to prevent the project from repeatedly reinventing:

- what `pump_vfd_debug` is,
- why it exists,
- how it is wired,
- how it is flashed,
- how it is reached over Wi-Fi,
- what API it exposes,
- what has already been confirmed on real `M980` hardware.

This document is about the debug firmware only.
It is not the production `pump_vfd` node and not the USB bridge path.

## Purpose

`pump_vfd_debug` is a standalone ESP32-based Modbus debug appliance for direct `M980` diagnostics.

It exists because the project needs a tool that can:

- talk directly to the VFD over RS485 / Modbus RTU,
- inspect live VFD state without the full bridge/host stack,
- read and write arbitrary holding registers,
- watch key register groups while buttons, selectors, and DI inputs are changed on the drive,
- reduce the need for repeated firmware rewrites during VFD bring-up.

This is the first-line field debug tool for `M980`.

## What It Is Not

`pump_vfd_debug` is not:

- the production `pump_vfd` firmware,
- the USB bridge,
- the host runtime,
- a truth source for physical pump behavior by itself.

It is a debug surface around Modbus-reported VFD state.

## Firmware Location

Source tree:

- [firmware/pump_vfd_debug/](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/firmware/pump_vfd_debug)

Build target:

- `pio run -d firmware/pump_vfd_debug`

Upload target:

- `pio run -d firmware/pump_vfd_debug -t upload --upload-port <serial-port>`

## Current Architecture

`pump_vfd_debug` uses:

- the repository Modbus transport model,
- direct ESP32 UART to RS485 transceiver wiring,
- `WiFiManager` for first-time Wi-Fi onboarding,
- a simple HTTP API for read/write/status/debug operations,
- local storage for configuration and preset watchlists.

Current internal parts:

- Modbus transport
- M980-specific debug driver
- Wi-Fi onboarding
- HTTP API
- config storage in `NVS`
- preset storage in `LittleFS`
- cached preset polling

## Confirmed MCU Pin Map

Current confirmed ESP32 pin map:

- `GPIO17 -> DI`
- `GPIO16 <- RO`
- `GPIO4 -> DE + RE`

These are confirmed against the current firmware and live hardware bring-up.

The previous reversed `DI/RO` wiring caused total Modbus read failure.

## Confirmed RS485 / VFD Wiring

Current confirmed field wiring for the working debug setup:

- `GPIO17 -> MAX485 DI`
- `GPIO16 <- MAX485 RO`
- `GPIO4 -> MAX485 DE + RE`
- `MAX485 A -> M980 S+`
- `MAX485 B -> M980 S-`
- common `GND` between ESP / transceiver side and VFD control side

Current transceiver used in field bring-up:

- ESP32 dev board
- `MAX485` TTL-to-RS485 module

What is still not frozen as canonical hardware truth:

- preferred decoupling layout,
- preferred termination/biasing policy,
- whether this exact module should remain the baseline transceiver recommendation.

## Confirmed Network Behavior

After Wi-Fi onboarding, the debug node is reachable by IP over HTTP.

Current confirmed behavior:

- HTTP API works over the assigned Wi-Fi IP
- `.local` name should not currently be assumed to work

Reason:

- `mDNS` publication has not yet been made canonical in the firmware

Practical rule:

- use the current IP address unless and until mDNS is intentionally added and verified.

## Confirmed VFD Communication Prerequisites

For direct Modbus communication to `M980`, the following have already been used successfully:

- `F7-00 = 1`
- `F7-01 = 0`
- `F7-02 = 3`

For first debug bring-up, it is acceptable to temporarily disable communication-timeout faulting:

- `F7-03 = 0.0`

This keeps `Err16` from interrupting initial wiring and register-map diagnostics.

## Confirmed Register Access Model

The debug firmware uses:

- Modbus function `0x03` for reads
- Modbus function `0x06` for writes

Current confirmed live register access examples:

- `0xF000 -> F0-00`
- `0xF001 -> F0-01`
- `0xF012 -> F0-18`
- `0xF014 -> F0-20`
- `0xF102 -> F1-02`
- `0xF108 -> F1-08`
- `0x1000 -> U0-00`
- `0x100B -> U0-11`
- `0x0003 -> relay/DO control register`

## Important M980 Register Mapping Finding

For this `M980`, parameter register addresses must not be treated as string-concatenated parameter labels.

The project originally assumed examples like:

- `F0-18 -> 0xF018`
- `F0-20 -> 0xF020`

That assumption was wrong for live `M980` register access.

Confirmed working mapping:

- `F0-18 -> 0xF012`
- `F0-20 -> 0xF014`

Interpretation:

- parameter numbers are effectively mapped by decimal parameter index into the low byte
- example:
  - `18 decimal = 0x12`
  - `20 decimal = 0x14`
  - `24 decimal = 0x18`

This finding is critical.
Any future `M980` register work must be checked against this rule before new assumptions are added to code or docs.

## Confirmed Relay1 Communication Control

`M980` relay output `T1A-T1B` can be used as a Modbus-controlled dry contact.

Current confirmed setup:

- `F1-08 = 7`

In this mode, relay1 is controlled through Modbus register:

- `0x0003`

Current confirmed behavior:

- `write 0x0003 = 1` -> relay1 closes
- `write 0x0003 = 0` -> relay1 opens

In the current field setup, `T1A-T1B` is wired into the `DI3` path.

This has already been confirmed live:

- `0x0003 = 1` -> `U0-11 = 4`
- `0x0003 = 0` -> `U0-11 = 0`

That means `pump_vfd_debug` can now switch the `DI3` path programmatically without manual shorting.

This is not just a manual-theory note.
It is a verified live hardware capability and should be considered available for future relay-driven tests and integration experiments.

## Current Supported API

Current working endpoints:

- `GET /api/status`
- `GET /api/watch`
- `GET /api/config`
- `POST /api/config/modbus`
- `POST /api/config/poll`
- `GET /api/presets`
- `GET /api/presets/get?name=<preset>`
- `POST /api/presets/save?name=<preset>&regs=<csv>`
- `POST /api/presets/load?name=<preset>`
- `GET /api/read?reg=<reg>`
- `GET /api/read_block?reg=<reg>&count=<count>`
- `POST /api/write?reg=<reg>&value=<value>`

## Current Endpoint Meaning

### `/api/status`

Returns:

- Wi-Fi status
- node IP
- Modbus config
- polling status
- active preset
- a runtime snapshot

### `/api/watch`

Returns:

- active preset name
- polling status
- last poll result
- cached values for the active preset

This is the main endpoint for watching live changes while pressing buttons or switching terminals on the VFD.

### `/api/config`

Returns current stored config:

- Modbus settings
- polling settings
- active preset name

### `/api/config/modbus`

Updates stored Modbus settings and reapplies them immediately:

- `slave_id`
- `baud`
- `timeout_ms`

### `/api/config/poll`

Updates:

- `enabled`
- `interval_ms`

### `/api/presets`

Lists preset names currently stored on the node.

### `/api/presets/get`

Returns the register list for one preset.

### `/api/presets/save`

Creates or replaces a preset from a CSV list of register addresses.

### `/api/presets/load`

Sets the active preset used by the polling engine.

### `/api/read`

Reads a single holding register.

### `/api/read_block`

Reads a block of consecutive holding registers.

### `/api/write`

Writes one holding register.

## Current Storage Model

### `NVS`

Stored in `Preferences`:

- Modbus slave id
- Modbus baud
- Modbus timeout
- poll enabled
- poll interval
- active preset name

### `LittleFS`

Stored in `presets.json`:

- preset register lists

## Current Built-In Presets

### `runtime`

- `0x1000`
- `0x1001`
- `0x1003`
- `0x1004`
- `0x1006`
- `0x100B`

### `mode-switch`

- `0xF000`
- `0xF001`
- `0xF012`
- `0xF014`
- `0xF105`
- `0xF106`
- `0x100B`

### `modbus`

- `0xF700`
- `0xF701`
- `0xF702`
- `0xF703`

### `motor`

- `0xF800`
- `0xF801`
- `0xF802`
- `0xF803`
- `0xF804`
- `0xF806`
- `0xF807`

## Current Field Workflow

### 1. Flash firmware

Example:

```bash
pio run -d firmware/pump_vfd_debug -t upload --upload-port /dev/cu.usbserial-0001
```

### 2. Join Wi-Fi

Use the firmware onboarding flow to place the ESP on the working Wi-Fi.

### 3. Find the IP

Use router/ARP discovery if needed.

Do not assume `.local` works yet.

### 4. Verify node health

Example:

```bash
curl http://<ip>/api/status
```

### 5. Verify VFD register access

Examples:

```bash
curl 'http://<ip>/api/read?reg=0xF700'
curl 'http://<ip>/api/read?reg=0x1000'
```

### 6. Watch live changes

Examples:

```bash
curl 'http://<ip>/api/presets/load?name=mode-switch' -X POST
curl 'http://<ip>/api/watch'
```

### 7. Read or write target parameters

Examples:

```bash
curl 'http://<ip>/api/read?reg=0xF102'
curl -X POST 'http://<ip>/api/write?reg=0xF102&value=20'
```

## Confirmed Live Findings

The following have already been confirmed on a live machine during bring-up:

- Wi-Fi connection works
- direct HTTP API works
- direct Modbus read/write works
- reversed `DI/RO` wiring causes total communication failure
- corrected `DI/RO` wiring restores communication
- `DI3` state is visible through `U0-11`
- with current test wiring:
  - `DI3` open -> `U0-11 = 0`
  - `DI3` closed -> `U0-11 = 4`
- `F0-00` and `F0-01` can be read live and match manual/remote mode changes
- `F0-18` can be read correctly at `0xF012`
- `F0-20` can be read correctly at `0xF014`
- `F1-02` can be read and written at `0xF102`
- `F1-08` can be read and written at `0xF108`
- `relay1` can be switched by writing `0x0003`
- `T1A-T1B` can be used to drive the current `DI3` path from Modbus control

## Confirmed Mode Pairing So Far

Currently confirmed live mode pairing:

- manual:
  - `F0-00 = 1`
  - `F0-01 = 1`
- remote Modbus:
  - `F0-00 = 2`
  - `F0-01 = 8`

These values are confirmed as readable live truth on the test `M980`.

## What Is Still Not Confirmed

The following are still open and must not be treated as settled truth yet:

- whether `DI3 function 20` is the final correct mode-switch function for this machine
- whether `F0-18 = 0820` alone is sufficient for clean DI-based switching
- whether a power-cycle or additional parameter is required for that switching behavior
- whether `F0-20 = 1` should be part of the canonical local/remote switching baseline
- the final host-side CLI for `pump_vfd_debug`
- OTA update support
- `mDNS` hostname publication

## Current Practical Rule

If `pump_vfd_debug` behavior and the existing docs disagree, prefer:

1. live verified register reads,
2. this file,
3. older `M980` mode-switch notes.

This document should be updated as new behavior is confirmed on real hardware, not by inference alone.
