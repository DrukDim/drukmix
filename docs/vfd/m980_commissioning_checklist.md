# M980 Commissioning Checklist

## Scope

This file is the short bring-up checklist for an `M980` used with the current `pump_vfd` path.

It covers three things:

- motor-side commissioning from factory reset to autotune;
- Modbus/RS485 setup required by current `pump_vfd` firmware;
- local-vs-Modbus mode switching needed for field bring-up.

It is intentionally shorter than the vendor manual.
Only settings that are confirmed by current firmware or directly supported by the vendor manual are listed here.

## 1. Factory reset

1. Power the VFD with the motor wiring disconnected or in a safe non-start state.
2. Reset parameters:
   - `F0-24 = 1`
3. Power-cycle if the drive/manual requires it after reset.

Source:
- [m980_mdriver_vfd_manual.pdf](/Users/dan/Library/Mobile%20Documents/com~apple~CloudDocs/Business/DrukDim/git/drukmix/docs/vfd/m980_mdriver_vfd_manual.pdf)

## 2. Motor nameplate entry

Before any autotune, enter the motor nameplate values:

- `F8-00` motor rated power
- `F8-01` motor rated voltage
- `F8-02` motor rated current
- `F8-03` motor rated frequency
- `F8-04` motor rated speed

These values must match the actual motor nameplate.
Do not guess them.

## 3. Autotune

Autotune parameter:

- `F8-07`

Modes confirmed by the manual:

- `0` -> no operation
- `1` -> static parameter identification
- `2` -> dynamic parameter identification

Use:

- `F8-07 = 1` when the motor cannot be fully separated from the load or cannot rotate freely.
- `F8-07 = 2` when the motor is mechanically disconnected from the load and can rotate freely.

Important vendor warning:

- the motor may rotate during autotune;
- do not place automatic switching devices between VFD and motor;
- keep people clear of the machine during tune.

After autotune, the drive may populate or refine asynchronous motor parameters such as:

- `F8-11`
- `F8-12`
- `F8-13`
- `F8-14`
- `F8-15`

## 4. Modbus settings required by current DrukMix firmware

Current `pump_vfd` firmware assumptions are:

- slave address `1`
- baud `9600`
- UART format `8N1`

That maps to these M980 settings:

- `F7-00 = 1` -> inverter address
- `F7-01 = 0` -> `9600 bps`
- `F7-02 = 3` -> `8-N-1`
- `F7-03` -> communication timeout

Recommended starting point:

- `F7-03 = 1.0 s`

Reason:

- `0.0 s` disables communication-timeout detection;
- values above `0.1 s` allow the VFD to raise communication fault `Err16` if traffic disappears.

## 5. Motor control mode: V/F or vector

M980 motor control parameter:

- `F8-06`

Vendor meanings:

- `0` -> `V/F` control
- `1` -> vector speed control of asynchronous motor
- `2` -> vector speed control of synchronous motor

For a standard asynchronous motor driving a gerotor/progressive-cavity pump with:

- heavy mixture,
- frequent frequency changes,
- low-speed load sensitivity,
- continuous Modbus speed control,

the recommended starting point is:

- `F8-06 = 1`

Reason:

- better low-speed torque behavior;
- better load regulation when the mix gets heavier;
- better match for frequent speed changes than plain `V/F`.

Fallback:

- if vector mode becomes unstable,
- or autotune cannot be completed correctly,
- or the motor data is not trustworthy,

fall back temporarily to:

- `F8-06 = 0`

and treat that as a degraded-but-simple baseline while the motor data and tuning are corrected.

Important:

- if `F8-06 = 1`, perform `F8-07` parameter identification after entering the motor nameplate values.

## 6. Modbus control mode required by DrukMix

For DrukMix control over Modbus:

- `F0-00 = 2` -> command source = communication control
- `F0-01 = 8` -> frequency source = communication setting

This is the canonical remote mode for the current `pump_vfd` firmware.

## 7. Current proven manual/auto pairing

The currently proven field pairing is:

- local/manual:
  - `F0-00 = 1`
  - `F0-01 = 1`
- remote/Modbus:
  - `F0-00 = 2`
  - `F0-01 = 8`

Meaning:

- local manual = terminal command + panel potentiometer
- remote auto = communication command + communication setting

## 8. Bind command source to frequency source

The key parameter for clean switching is:

- `F0-18`

For the current proven pairing, set:

- `F0-18 = 820`

Meaning:

- terminal command binds to panel potentiometer
- communication command binds to communication setting

This is what makes one mode-switch input enough.

## 9. Switching manual/auto modes

For the current proven pairing, use:

- one DI terminal with function `20`

Vendor meaning:

- command source switching terminal 2
- external terminal control <-> communication command control

This is the correct mode switch because the local side is terminal command, not keyboard command.

Do **not** use DI function `19` for this case.

## 10. Universal stop input

If you want one stop input that works regardless of the currently selected command source, use a DI terminal function:

- `13` -> external terminal shutdown, valid at any time

This is the cleanest candidate for a non-emergency universal stop because it is documented as valid at any time and uses deceleration time 2.

Related functions:

- `12` -> coast stop
- `14` -> emergency stop

For pump work, `13` is the better default starting point unless you explicitly need coast stop or emergency stop behavior.

If you want the front STOP key to stay effective in every mode, set:

- `F0-20 = 1`

## 11. Practical bring-up order

1. Factory reset with `F0-24 = 1`.
2. Enter motor nameplate `F8-00` ... `F8-04`.
3. Select motor control mode:
   - recommended start: `F8-06 = 1`
   - fallback: `F8-06 = 0`
4. Run autotune using `F8-07 = 1` or `2` as appropriate.
5. Confirm motor can run safely in local mode first.
6. Set Modbus parameters:
   - `F7-00 = 1`
   - `F7-01 = 0`
   - `F7-02 = 3`
   - `F7-03 = 1.0 s` as the initial value
7. Set the currently proven local manual mode:
   - `F0-00 = 1`
   - `F0-01 = 1`
8. Set remote DrukMix mode:
   - `F0-00 = 2`
   - `F0-01 = 8`
9. Set command/frequency binding:
   - `F0-18 = 820`
10. Assign one DI terminal to function `20` for manual/Modbus mode switching.
11. If you need one universal stop input, assign another DI terminal to function `13`.
12. If you want the front STOP key always active, set `F0-20 = 1`.
13. Only after that move on to ESP/RS485 wiring and live Modbus tests.

## 12. Open gaps

This checklist still does not freeze:

- the exact preferred deceleration/stop parameters for concrete pumping;
- the exact DI terminal chosen in field wiring for local/remote switching;
- the exact electrical wiring used for the manual/Modbus selector on this machine;
- whether additional VFD-side protection or fault-reset policy should be part of the canonical baseline.

Those should be added only after they are confirmed on real hardware.
