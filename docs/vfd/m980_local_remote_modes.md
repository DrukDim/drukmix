# M980 Local and Remote Modes

## Scope

This file defines the currently proven local/manual and remote/Modbus mode pairing for the `M980`.

The main point is simple:

- local/manual and remote/Modbus are not only different command sources;
- they may also need different frequency sources;
- the clean solution is to use command/frequency binding, not just `F0-00` alone.

## Current proven local/manual mode

The currently proven local mode on this machine is:

- `F0-00 = 1`
- `F0-01 = 1`

Meaning:

- command source = terminal control
- frequency source = panel potentiometer

This matches the observed field behavior:

- `FWD / STOP / REV` works;
- the potentiometer also works correctly.

## Current remote/Modbus mode

The current remote mode for DrukMix is:

- `F0-00 = 2`
- `F0-01 = 8`

Meaning:

- command source = communication control
- frequency source = communication setting

## Parameter that makes switching clean

The missing parameter is:

- `F0-18`

Vendor meaning:

- ones digit = panel command binding frequency source
- tens digit = terminal command binding frequency source
- hundreds digit = communication command binding frequency source

For the current proven pairing, use:

- `F0-18 = 820`

Meaning:

- panel binding = `0` -> no binding
- terminal binding = `2` -> panel potentiometer
- communication binding = `8` -> communication setting

With this in place:

- terminal command automatically uses the panel potentiometer;
- communication command automatically uses communication frequency;
- one command-source switch input is enough for mode switching.

## DI function for mode switching

For the current proven pairing, use:

- `20` -> command source switching terminal 2

Reason:

- local/manual command source is terminal control;
- remote/auto command source is communication control.

Function `19` is not the right one here.
It is for keyboard/panel switching, not terminal-vs-communication switching.

## Recommended practical mode set

Program these values:

- local/manual baseline:
  - `F0-00 = 1`
  - `F0-01 = 1`
- remote/Modbus baseline:
  - `F0-00 = 2`
  - `F0-01 = 8`
- binding:
  - `F0-18 = 820`
- mode switch input:
  - one DI terminal = function `20`

## Universal stop

If you need one stop input that works regardless of current command source, use another DI terminal with:

- `13` -> external terminal shutdown, valid at any time

If you also want the front STOP key to work in every mode, set:

- `F0-20 = 1`

## Wiring implication

For this mode model:

- one DI input is needed for manual/Modbus switching;
- one separate DI input is recommended for universal stop.

If your hardware switch has only one changeover contact `NO / S / NC`, it is suitable for the mode switch alone.
Do not try to combine mode switch and universal stop into the same single contact.
