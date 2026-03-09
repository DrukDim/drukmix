# VFD Fault Map and Operator Policy

## Automatic policy

### Allowed automatic reset
Only `Err16` may be auto-reset automatically, and only once during startup/reconnect.

Conditions:
- VFD is not actively running
- print is not active
- communication is already restored
- reset is attempted only once per startup cycle

All other faults:
- never auto-reset
- must be exposed to operator
- if printing: pause print and stop pump

---

## Fault quick policy table

| Code | Name | Auto reset | Pause print | Notes |
|---|---|---:|---:|---|
| Err01 | Inverter Unit Protection | no | yes | hard fault |
| Err02 | Overcurrent During Acceleration | no | yes | hard fault |
| Err03 | Overcurrent During Deceleration | no | yes | hard fault |
| Err04 | Overcurrent at Constant Speed | no | yes | hard fault |
| Err05 | Overvoltage During Acceleration | no | yes | hard fault |
| Err06 | Overvoltage During Deceleration | no | yes | hard fault |
| Err07 | Overvoltage at Constant Speed | no | yes | hard fault |
| Err08 | Control Power Supply Fault | no | yes | hard fault |
| Err09 | Undervoltage | no | yes | power issue |
| Err10 | Inverter Overload | no | yes | overload |
| Err11 | Motor Overload | no | yes | overload |
| Err12 | Power Input Phase Loss | no | yes | power issue |
| Err13 | Power Output Phase Loss | no | yes | motor/output issue |
| Err14 | Module Overheat | no | yes | thermal |
| Err15 | External Equipment Fault | no | yes | external fault input |
| Err16 | Communication Fault | yes, once | yes if persists | startup race is safe-reset case |
| Err17 | Contactor Fault | no | yes | hardware |
| Err18 | Current Detection Fault | no | yes | hardware |
| Err19 | Motor Auto-tuning Fault | no | no | setup/tuning |
| Err21 | EEPROM Write Fault | no | yes | hardware |
| Err22 | Inverter Hardware Fault | no | yes | hardware |
| Err23 | Short Circuit to Ground | no | yes | severe |
| Err26 | Accumulative Running Time Reached | no | no | service/info |
| Err29 | Accumulative Power-on Time Reached | no | no | service/info |
| Err40 | Pulse-by-pulse Current Limit Fault | no | yes | overload |
| Err41 | Motor Switchover Fault During Running | no | yes | control misuse |
| Err42 | Excessive Speed Deviation Fault | no | yes | tuning/control |
| A52 | Water Shortage Alarm | no | optional | application-specific alarm |
| Err53 | Overpressure Fault | no | yes | process alarm |
| Err56 | Knitting Machine DI Fault | no | no | DI config issue |
| Err64 | Internal Communications Fault | no | yes | hardware/internal |
| Err65 | Power Board Communication Fault | no | yes | hardware/internal |

---

## Project-specific note for Err16

In this project `Err16` is usually caused by VFD booting earlier than ESP/backend and missing communication for the first 1-2 seconds.

This specific startup case is safe to reset automatically once.

If `Err16` persists after one automatic reset attempt:
- do not auto-reset again
- expose fault to operator
- pause print if printing is active
- require manual intervention
