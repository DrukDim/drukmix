# M980 Local and Remote Modes

## Scope

This file exists to prevent one very specific bring-up mistake:

- confusing panel control with terminal control.

For the current `M980` field workflow there are two distinct operating modes.

## Remote DrukMix mode

When DrukMix controls the VFD through Modbus RTU:

- `F0-00 = 2`
- `F0-01 = 8`

Meaning:

- command source = communication control
- frequency source = communication setting

## Local manual mode

When the operator uses:

- a potentiometer for speed;
- a physical forward/stop/reverse switch;

the local mode is:

- `F0-00 = 1`
- `F0-01 = 2`

Meaning:

- command source = terminal control
- frequency source = `AI1`

## Important non-rule

`F0-00 = 0`, `F0-01 = 2` is **not** the same thing.

That combination means:

- run/stop from the keypad panel;
- frequency from `AI1`

It does not match a local hardware `FWD/STOP/REV` switch as the command source.

## DI switching function

If one external button/switch should toggle between:

- terminal control
- communication control

then the relevant DI function is:

- `20` -> command source switching terminal 2

This is the vendor-documented mode switch for:

- external terminal control <-> communication command control

## What function 19 is for

DI function `19` is different:

- it switches keyboard and the currently active external/communication command source

That is not the clean local-terminal-vs-Modbus selector for this workflow.
