# M900 / M980 shared semantics

## Scope

Це спільна семантична база для DrukMix driver contract під M900 і M980.

## Shared control model

### Command source
- `F0-00 = 0` -> panel control
- `F0-00 = 1` -> terminal control
- `F0-00 = 2` -> communication control (Modbus RTU / RS485)

### Frequency source
- Communication settings можуть бути джерелом частоти.
- Для обох серій це пов'язано з `F0-01` / binding semantics.

### Stop semantics
- `ramp stop`
- `coast stop`

### Factory reset
- `F0-24 = 1` -> factory reset

### Fault reset
- DI function `7` = fault reset

### Monitoring semantics
Базові register-и моніторингу для обох серій співпадають по змісту:
- `1000H` -> running state
- `1001H` -> fault code
- `1003H` -> running frequency
- `1004H` -> running speed
- `1006H` -> output current

## Important rule for DrukMix

`running == true` не означає, що вал реально крутиться.

Для логіки DrukMix потрібно розділяти:
- logical run state
- actual output frequency
- output current
- active fault code

## Recovery rule

Після reset fault не вважати VFD "нормально відновленим" тільки по біту running.

Потрібно переперевірити:
- fault code
- actual frequency
- output current
- чи не залишився cmd setpoint == 0 при `running == true`

## Current project implication

Автоскидання допускається тільки для communication-loss class fault.
Process faults, overload, overpressure, water shortage та інші fault-и не автоскидати без окремо описаної policy.
