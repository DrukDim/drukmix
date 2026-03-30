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

## Confirmed Relay Communication Control

`M980` relay outputs `T1A-T1B` and `T2A-T2B` can be used as Modbus-controlled dry contacts.

Current confirmed setup:

- `F1-08 = 7`
- `F1-09 = 7`

In this mode, relay outputs are controlled through Modbus register:

- `0x0003`

Bit meaning confirmed in field:

- bit `0` -> relay1
- bit `1` -> relay2

Current confirmed behavior:

- `write 0x0003 = 1` -> relay1 closes
- `write 0x0003 = 2` -> relay2 closes
- `write 0x0003 = 3` -> relay1 and relay2 close
- `write 0x0003 = 0` -> relay1 and relay2 open

Current field wiring:

- `T1A-T1B` is wired into the `DI3` path
- `T2A-T2B` is wired into the `DI4` path

This has already been confirmed live:

- `0x0003 = 1` -> `U0-11 = 4`
- `0x0003 = 2` -> `U0-11 = 8`
- `0x0003 = 3` -> `U0-11 = 12`
- `0x0003 = 0` -> `U0-11 = 0`

That means `pump_vfd_debug` can now switch `DI3` and `DI4` programmatically without manual shorting.

This is a verified live hardware capability and should be considered available for future relay-driven tests and integration experiments.

## Control-Model Picture

The current M-Driver family picture must be treated as four separate layers, not one mode bit.

### 1. Command source

Primary objects:

- `F0-00`
- DI function `20`

Meaning:

- who owns run/stop/reverse authority

### 2. Frequency source

Primary objects:

- `F0-01` main frequency source
- `F0-02` auxiliary frequency source
- `F0-03` logic between main and auxiliary source
- DI function `24`

Meaning:

- who owns the effective target frequency

### 3. Binding

Primary object:

- `F0-18`

Meaning:

- optional binding between panel / terminal / communication command channels and one frequency source

Important:

- `F0-18` is not the same thing as full command/reference channel selection
- current field work shows that treating `F0-18` as the only solution path is unsafe

### `F0-18` detail

Current best interpretation is that `F0-18` is a three-digit binding code shown on the panel as a zero-padded four-character field.

Current structure:

- ones digit = panel-command binding frequency source
- tens digit = terminal-command binding frequency source
- hundreds digit = communication-command binding frequency source

Current manual-derived digit map:

- `0` = no binding
- `1` = panel up/down key source
- `2` = panel potentiometer
- `3` = `AI1`
- `4` = reserved
- `5` = multi-step / multi-speed
- `6` = `PLC`
- `7` = constant-pressure / water-supply PID
- `8` = general PID
- `9` = communication setting

Important:

- this digit map must not be casually conflated with the `F0-01` / `F0-02` source list shown on the live panel
- current field work already showed that `F0-01` / `F0-02` semantics and `F0-18` digit semantics must be treated as related but not assumed identical

Current panel-format rule:

- the panel displays values like `0020`, `0800`, `0820`, `0900`, `0920`
- Modbus readback at `0xF012` returns the same values as plain integers:
  - `20`
  - `800`
  - `820`
  - `900`
  - `920`

Current field conclusion about the fourth displayed digit:

- there is no confirmed evidence that the leading displayed zero is a fourth semantic binding digit
- current evidence supports treating it as fixed-width zero padding
- this is still a field conclusion, not a vendor-proven formal rule

Current field conclusion about practical effect:

- `F0-18` does affect behavior
- but across the tested values above it has not yet restored the required hybrid manual mode:
  - built-in selector works
  - built-in potentiometer works
- for this use case, `F0-18` must currently be treated as a modifier, not as a proven full solution

### 4. Terminal logic

Primary objects:

- `F1-05`
- `F1-06`

Meaning:

- DI polarity and two-wire / three-wire terminal semantics

Current confirmed live values:

- `F1-05 = 0`
- `F1-06 = 0`

These matter for DI behavior, but current evidence does not support them as the missing communication-frequency gate.

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

Important:

- this built-in preset is historical
- it is still useful for quick live checks
- it is not sufficient for the current full local/manual vs auto/Modbus research

For current mode-switch investigation, also inspect:

- `0xF002 -> F0-02`
- `0xF003 -> F0-03`
- `0xF102 -> F1-02`
- `0xF103 -> F1-03`
- `0xF108 -> F1-08`
- `0xF109 -> F1-09`

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
- `DI4` state is visible through `U0-11`
- with current test wiring:
  - `DI3` open -> `U0-11 = 0`
  - `DI3` closed -> `U0-11 = 4`
  - `DI4` closed -> `U0-11 = 8`
  - `DI3 + DI4` closed -> `U0-11 = 12`
- `F0-00` and `F0-01` can be read live and match manual/remote mode changes
- `F0-02` and `F0-03` can be read live and must be tracked during source-switch tests
- `F0-18` can be read correctly at `0xF012`
- `F0-20` can be read correctly at `0xF014`
- `F1-02` can be read and written at `0xF102`
- `F1-03` can be read and written at `0xF103`
- `F1-08` can be read and written at `0xF108`
- `F1-09` can be read and written at `0xF109`
- `relay1` can be switched by writing `0x0003`
- `relay2` can be switched by writing `0x0003`
- `T1A-T1B` can be used to drive the current `DI3` path from Modbus control
- `T2A-T2B` can be used to drive the current `DI4` path from Modbus control

## Confirmed Direct Baselines

### Direct manual baseline

The following baseline has been confirmed as a clean local/manual state:

- `F0-00 = 1`
- `F0-01 = 1`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 0`
- `F1-02 = 0`
- `F1-03 = 0`
- `DI3 open`
- `DI4 open`

Confirmed live behavior:

- local selector works
- local panel potentiometer works

### Direct communication baseline

The following baseline has been confirmed as a working direct communication state:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 0`
- `F0-03 = 0`

Confirmed live behavior:

- `0x0002` controls run/stop
- `0x0001` produces a real communication frequency output
- runtime registers report non-zero delivered frequency in this mode

This direct communication baseline is critical.
It proves that the `M980` communication-frequency path is real and working when the drive is placed into explicit communication mode.

### Direct profile switching without power-cycle

The following has now also been confirmed live:

- switching from the clean manual baseline to the clean direct communication baseline works without a drive power-cycle
- switching back from the clean direct communication baseline to the clean manual baseline also works without a drive power-cycle

Confirmed live sequence:

1. apply manual profile
2. verify selector + potentiometer
3. write full auto profile
4. verify Modbus run + delivered communication frequency
5. stop the drive fully
6. write full manual profile again
7. verify selector + potentiometer again

This is currently the strongest confirmed solution family for manual/auto switching.

## Confirmed DI Function Behavior

### `DI3 = 20`

Current confirmed interpretation:

- DI function `20` is command-side switching only

What has been confirmed live:

- `DI3 active` changes effective run/stop ownership
- this can happen even when `F0-00` does not rewrite itself live
- `DI3` alone does not make communication frequency work reliably

### `DI4 = 24`

Current confirmed interpretation:

- DI function `24` does affect the frequency-side selection state
- but current field work has not yet produced a clean full auto-frequency result from `DI4` alone or from `DI3 + DI4`

### Practical rule

For this project, behavior must be validated by:

- actual motor response
- delivered runtime registers such as `U0-*`
- not only by static reads of `F0-00`, `F0-01`, `F0-02`, `F0-03`, or `F0-18`

## Research Findings From Official Family Docs

The current research base is:

- official M-Driver `900` family manual
- official M-Driver configurator / scenario / package docs
- official Schneider separate command/reference docs used only as architecture analogy
- live field tests on the current `M980`

### What official M-Driver docs clearly say

- explicit communication mode is:
  - `F0-00 = 2`
  - `F0-01 = 8`
- in that mode:
  - `0x0002` controls start/stop
  - `0x0001` controls target frequency
- DI function `20` switches command source
- DI function `24` switches frequency source
- `F0-18` is a binding parameter, not an explicit full profile switch

### What official M-Driver docs do not currently prove

- they do not provide a confirmed one-button recipe showing that `DI20 + DI24 + F0-18`
  is fully equivalent to:
  - `F0-00 = 2`
  - `F0-01 = 8`
- they do not currently prove that the communication-frequency path becomes fully active
  just because command source was switched by DI
- they do not currently prove that `F0-18` can replace full command/reference profile switching for this use case

### What the Schneider analogy changes

Schneider official docs make a much stronger distinction between:

- command channel
- reference channel
- explicit local/remote switching between them

That does not prove `M980` is a Schneider clone.
But it does show that the correct engineering question is:

- is `M980` really capable of the same full dual-channel switching behavior through `DI20/24`
- or does it require explicit profile changes to enter real communication mode

Current field evidence points more strongly to the second possibility than to the first.

## MDRIVERcfg / Scenario Finding

The local `MDRIVERcfg` archive in this repository is important evidence.

The so-called scenarios are not currently evidenced as free-form runtime logic.
What can already be seen from the shipped files is:

- `SCEN/WaterPressure.csv` is a parameter batch file made of `address;value` rows
- `REDY_SYS/st.csv`, `strv.csv`, `strvpt.csv` are canned parameter-set profiles

This is important because it suggests that M-Driver's own tooling already thinks in terms of:

- parameter-set loading
- prepared profile packages

more than in terms of undocumented hidden DI magic.

This does not prove runtime switching.
But it strongly supports the idea that profile-level parameter switching is a vendor-native concept.

## Rejected Or Weakened Hypotheses

The following hypotheses are now weak enough that they must not be treated as likely truths.

### `F0-18 = 0820` as the main solution

Rejected.

Reasons:

- it was based on a wrong semantic read of the communication digit
- later field work showed it should not be treated as canonical truth

### `F0-18 = 0920` as the main solution

Rejected.

Confirmed live effect:

- local selector still works
- local panel potentiometer stops working

That means `920` breaks a clean manual baseline.

### `F0-18 = 0900` as the main solution

Weakened / not sufficient.

Confirmed live effect:

- it does not break the clean manual baseline
- but with `DI3 = 20` only, it still does not produce a working communication frequency output

### `F0-18 = 0800` or `0820` as the main solution

Rejected / not sufficient.

Confirmed live effect on auto-first tests:

- built-in selector works after `DI3 = 20`
- built-in potentiometer still does not work

That means these values also fail to restore the required hybrid manual mode.

### `DI3 = 20` alone is enough

Rejected.

Confirmed live result:

- `DI3` can switch effective command ownership
- it does not by itself reproduce working communication frequency behavior

### `DI3 = 20` + `DI4 = 24` is already solved

Rejected.

Current field work shows this path is still incomplete.

## Current Strongest Interpretations

### Interpretation A: explicit communication mode is a hard gate

This is currently the strongest interpretation.

Meaning:

- `0x0001` is truly effective only when the drive is in full explicit communication mode
- that means:
  - `F0-00 = 2`
  - `F0-01 = 8`

This interpretation matches:

- official M-Driver communication-enable docs
- current direct communication field tests
- current failure of `DI3`-only and `DI3 + DI4` to reproduce the same result

### Interpretation B: pure DI-only switching may be insufficient

Current probability: medium to high.

Meaning:

- even though `DI20` and `DI24` exist,
- they may not be enough to recreate full communication mode for this exact use case

### Interpretation B1: `F0-18` terminal-binding digit may be the key missing gate

Current probability: medium to high.

Meaning:

- current field work now shows a strong distinction between:
  - `F0-18 = 1`
  - and `F0-18 = 10`
- with `DI3 = 20` active in an auto-first profile, `1` is not enough to make the built-in potentiometer effective
- but `10` is enough to make the built-in potentiometer effective while preserving selector-driven command behavior

This is now the strongest live clue that the effective binding for the required hybrid manual override may sit specifically in the terminal-binding digit, not in the panel-binding digit.

### Interpretation C: profile switching may be the real solution family

Current probability: high.

Meaning:

- working manual and working auto may need to be treated as two explicit full parameter profiles
- switching might need to happen by:
  - controller-driven parameter writes,
  - vendor runtime logic if supported,
  - or another higher-level mechanism

This interpretation is now strengthened by live proof that:

- `manual profile -> auto profile -> manual profile`
- works in both directions
- without a power-cycle
- while preserving the expected behavior on both sides

## Test Ledger

This section is the canonical test memory.
New tests must be appended here instead of being left only in chat history.

### T001 - Wiring correction

Result:

- reversed `DI/RO` wiring caused total Modbus failure
- corrected `GPIO17 -> DI`, `GPIO16 <- RO` restored communication

### T002 - Register map correction

Result:

- `F0-18` is `0xF012`, not `0xF018`
- `F0-20` is `0xF014`, not `0xF020`

### T003 - DI state readback

Result:

- `DI3 active` -> `U0-11 = 4`
- `DI4 active` -> `U0-11 = 8`
- both active -> `U0-11 = 12`

### T004 - Relay-driven DI switching

Result:

- `F1-08 = 7` and `F1-09 = 7` make relay1/relay2 controllable from `0x0003`
- relay1 can drive `DI3`
- relay2 can drive `DI4`

### T005 - Clean manual baseline

Parameters:

- `F0-00 = 1`
- `F0-01 = 1`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 0`
- `F1-02 = 0`
- `F1-03 = 0`

Result:

- local selector works
- local potentiometer works

### T006 - Direct communication baseline

Parameters:

- `F0-00 = 2`
- `F0-01 = 8`

Result:

- `0x0002` run/stop works
- `0x0001` gives real delivered frequency

### T007 - `F0-18 = 920`

Result:

- breaks clean manual baseline
- selector still works
- panel potentiometer stops working

### T008 - `F0-18 = 900`

Result:

- does not break clean manual baseline
- still does not make `DI3 = 20` sufficient for communication frequency

### T009 - `DI3 = 20` only

Result:

- command-side switching confirmed
- communication frequency not confirmed

### T010 - `DI3 = 20`, `DI4 = 24`, `F0-01 = 1`, `F0-02 = 8`, `F0-03 = 2`

Result:

- this path is still incomplete
- it has not yet reproduced the same behavior as the direct communication baseline

### T011 - Full-profile switching without power-cycle

Manual profile:

- `F0-00 = 1`
- `F0-01 = 1`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 0`
- `F1-02 = 0`
- `F1-03 = 0`

Auto profile:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 0`
- `F1-02 = 0`
- `F1-03 = 0`

Result:

- drive accepts full profile rewrite without power-cycle
- auto profile gives real Modbus frequency output
- after full stop, manual profile can be restored by parameter writes only
- local selector and local potentiometer work again after the return to manual

### T012 - `panel-manual` split proof

Parameters:

- `F0-00 = 0`
- `F0-01 = 1`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 0`
- `F1-02 = 0`
- `F1-03 = 0`

Result:

- built-in potentiometer works
- built-in selector does not work

Meaning:

- built-in potentiometer belongs to the panel-frequency side
- built-in selector is not a pure panel-command control path

### T013 - Auto-first single-DI binding series

Base profile:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 0`
- `F0-03 = 0`
- `F1-02 = 20`
- `F1-03 = 0`
- `DI3 active`

Tested `F0-18` values:

- `20`
- `800`
- `820`
- `900`
- `920`

Result:

- built-in selector works
- built-in potentiometer does not work

Meaning:

- in the tested auto-first single-DI architecture, `F0-18` can influence command-side override behavior
- but it has not restored the built-in potentiometer alongside the selector

### T014 - Auto-first dual-source binding series

Base profile:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 1`
- `F0-03 = 2`
- `F1-02 = 20`
- `F1-03 = 24`
- `DI3 active`
- `DI4 active`

Tested `F0-18` values:

- `0`
- `800`
- `820`
- `900`
- `920`

Result:

- built-in selector works
- built-in potentiometer does not work

Meaning:

- even with explicit `DI24` frequency switching and a dual-source profile,
- the tested `F0-18` variants did not restore the required hybrid manual mode

### T015 - Terminal-binding isolation inside `F0-18`

Base profile:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 0`
- `F0-03 = 0`
- `F1-02 = 20`
- `F1-03 = 0`

Manual-side test setup:

- `DI3 active`
- selector in `FWD`
- built-in potentiometer around mid position

Observed results:

- `F0-18 = 1`
  - `run_state = 1`
  - `actual_freq = 0`
  - `speed = 0`
  - `current = 4`
  - `U0-11 = 5`
- `F0-18 = 10`
  - `run_state = 1`
  - `actual_freq = 109` and later `141`
  - `speed = 364` and later `374`
  - `current = 4`
  - `U0-11 = 5`
- `F0-18 = 11`
  - same effective delivered result as `10`
- `F0-18 = 12`
  - same effective delivered result as `10`
- `F0-18 = 19`
  - same effective delivered result as `10`

Meaning:

- the decisive change is the tens digit, not the ones digit
- current evidence points to the terminal-binding digit as the relevant gate for restoring the built-in potentiometer during manual override
- the ones digit did not materially change delivered behavior in the tested `1x` set

### T016 - Auto-side confirmation with `F0-18 = 10`

Base profile:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 10`
- `F1-02 = 20`
- `F1-03 = 0`

Auto-side test setup:

- `DI3 open`
- local selector in `STOP`
- built-in potentiometer at `0`

Observed result:

- after Modbus `0x0001 = 500`, `0x0002 = 1`:
  - `run_state = 1`
  - `actual_freq = 25`
  - `speed = 66`
  - `current = 5`
  - `U0-11 = 0`

Meaning:

- `F0-18 = 10` did not break the direct communication-side workflow
- with `DI3 open`, command and frequency authority still follow Modbus in the tested auto-first profile

### T017 - Repeated `DI3` operator workflow cycles with `F0-18 = 10`

Base profile:

- `F0-00 = 2`
- `F0-01 = 8`
- `F0-02 = 0`
- `F0-03 = 0`
- `F0-18 = 10`
- `F1-02 = 20`
- `F1-03 = 0`

Fixed physical setup for the series:

- selector in `FWD`
- built-in potentiometer around mid position

Observed runtime sequence:

- `baseline_open_stopped`
  - `run_state = 3`
  - `actual_freq = 0`
  - `speed = 0`
  - `current = 0`
  - `di_state = 1`
- `cycle1_manual_active`
  - `run_state = 1`
  - `actual_freq = 130`
  - `speed = 421`
  - `current = 4`
  - `di_state = 5`
- `cycle1_auto_open_run500`
  - `run_state = 1`
  - `actual_freq = 25`
  - `speed = 66`
  - `current = 3`
  - `di_state = 1`
- `cycle2_manual_active`
  - `run_state = 1`
  - `actual_freq = 155`
  - `speed = 487`
  - `current = 4`
  - `di_state = 5`
- `cycle2_auto_open_run800`
  - `run_state = 1`
  - `actual_freq = 40`
  - `speed = 106`
  - `current = 5`
  - `di_state = 1`

Final-stop note:

- the scripted final read timed out after the last `STOP`
- separate direct `curl` reads immediately after that timeout confirmed:
  - `run_state = 3`
  - `actual_freq = 0`
  - `speed = 0`
  - `current = 0`

Meaning:

- `F0-18 = 10` survived repeated `manual -> auto -> manual -> auto` switching through `DI3`
- manual-side delivered behavior tracks the built-in selector and potentiometer
- auto-side delivered behavior tracks Modbus setpoint changes
- this is currently the strongest confirmed operator-workflow candidate found in field tests

## Open Questions

The following are still open and must not be treated as settled truth yet:

- whether `DI20/24` can ever reproduce the direct communication baseline without explicit `F0-00 = 2`, `F0-01 = 8`
- whether `F0-18 = 10` is the minimal final working value or just the first confirmed member of a broader working family
- whether there is another required gate parameter near the source-selection group
- whether vendor internal PLC/runtime logic can switch full profiles from DI state
- whether a controller-driven full-profile switch is the final practical solution
- the final host-side CLI for `pump_vfd_debug`
- OTA update support
- `mDNS` hostname publication

## Next Test Matrix

Future tests should not be ad hoc.
They should be grouped by solution family.

### Family A - Binding family

Purpose:

- finish evaluating `F0-18` systematically instead of by random guesses

Rules:

- always test against a known clean manual baseline first
- vary `F0-18` together with a clearly declared `F0-00..F0-03` profile
- record whether manual selector, manual pot, Modbus run, and Modbus frequency each work

Current narrowed focus inside this family:

- do not keep re-testing `20 / 800 / 820 / 900 / 920` in the already-covered base profiles above
- prefer terminal-binding isolation tests before broad new brute-force sweeps
- if binding-family testing continues, it should target genuinely new combinations such as:
  - different terminal-binding candidates around the now-confirmed working `1x` family
  - different communication-binding digit candidates once the terminal-binding side is stabilized
  - different declared `F0-00..F0-03` source architectures
- every new test must state exactly which family/profile it belongs to

### Family B - Explicit DI family

Purpose:

- continue `DI20` / `DI24` testing as a command/reference architecture problem

Rules:

- test complete profiles, not isolated single values only
- always record:
  - `F0-00`
  - `F0-01`
  - `F0-02`
  - `F0-03`
  - `F0-18`
  - `F1-02`
  - `F1-03`
  - `F1-05`
  - `F1-06`
  - `U0-11`
  - delivered runtime registers

### Family C - Full-profile switching family

Purpose:

- test whether the real solution is explicit switching between:
  - manual profile
  - direct communication profile

Status:

- this family is now confirmed as working in principle
- remaining work is not proof-of-possibility, but integration design

Candidate profiles:

- manual:
  - `F0-00 = 1`
  - `F0-01 = 1`
- auto:
  - `F0-00 = 2`
  - `F0-01 = 8`

Next questions for this family:

- who owns the rewrite:
  - ESP debug / future pump node
  - bridge / host
  - vendor runtime logic inside the drive
- what safety handshake is required before applying the profile change
- how to guarantee fail-safe return to manual if upstream control disappears

Constraint:

- this family is not currently acceptable as the final operator-fallback solution by itself
- a dead ESP / dead upstream controller is a real field condition
- the final production solution must still provide a physical path back to safe manual control without menu editing

### Family D - Vendor runtime logic / PLC family

Purpose:

- test whether internal M-Driver runtime logic can switch or emulate the required profiles

Rules:

- do not assume `MDRIVERcfg` package files are runtime logic
- confirm first whether a given mechanism is:
  - offline parameter package loading
  - or actual runtime logic

## Current Practical Rule

If `pump_vfd_debug` behavior and the existing docs disagree, prefer:

1. live verified register reads,
2. this file,
3. older `M980` mode-switch notes.

Additional rule:

- neighboring docs that still present `F0-18 = 820` as settled truth must be treated as historical until updated against this file

This document should be updated as new behavior is confirmed on real hardware, not by inference alone.
