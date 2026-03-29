# M980 Local and Remote Modes

## Scope

This file exists to prevent one very specific bring-up mistake:

- confusing panel control with terminal control.

For the current `M980` field workflow there are two distinct families of operating modes:

- panel-manual vs Modbus-remote;
- terminal-manual vs Modbus-remote.

## Remote DrukMix mode

When DrukMix controls the VFD through Modbus RTU:

- `F0-00 = 2`
- `F0-01 = 8`

Meaning:

- command source = communication control
- frequency source = communication setting

## Panel-manual mode

This is the mode to use when the operator uses the drive's own front controls:

- front potentiometer or built-in analog speed control;
- front `FWD / STOP / REV` selector or keypad-side run controls.

The manual meaning is:

- `F0-00 = 0` -> panel command source

For some field setups, local frequency is still intentionally taken from `AI1`:

- `F0-01 = 2`

That combination means:

- run/stop from the panel;
- frequency from `AI1`

This is the correct local-manual interpretation if the local speed control is effectively routed through the drive-side analog input rather than through a pure keypad potentiometer mode.

## Terminal-manual mode

When the operator uses:

- a potentiometer for speed;
- a physical forward/stop/reverse switch;

the local mode is:

- `F0-00 = 1`
- `F0-01 = 2`

Meaning:

- command source = terminal control
- frequency source = `AI1`

## Important distinction

- `F0-00 = 0`, `F0-01 = 2` means panel-manual command with `AI1` frequency source.
- `F0-00 = 1`, `F0-01 = 2` means terminal-manual command with `AI1` frequency source.

They are not the same mode.

## DI switching for panel-manual <-> Modbus-remote

If one external button/switch should toggle between:

- keyboard / panel-manual control
- communication control

then the relevant DI function is:

- `19` -> running command switch terminal 1

This is the vendor-documented mode switch for keyboard vs communication selection when `F0-00 = 2`.

Practical rule:

- default state can remain `F0-00 = 2` for Modbus control;
- when the DI becomes valid, the drive switches to keyboard / panel-manual command;
- when it becomes invalid again, it returns to communication command.

## DI switching for terminal-manual <-> Modbus-remote

If one external button/switch should toggle between:

- terminal control
- communication control

then the relevant DI function is:

- `20` -> command source switching terminal 2

This is the vendor-documented mode switch for:

- external terminal control <-> communication command control
