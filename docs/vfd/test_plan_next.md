# VFD next test plan

## A. Fault reset validation
- reproduce Err16 by power/link order mismatch
- send one reset-fault from host/bridge
- confirm:
  - fault goes 16 -> 0
  - command path survives
  - no unwanted motor spin
  - no repeated reset loop

## B. Less aggressive reset sequence candidates
Compare:
1. STOP -> RESET -> STOP   (current)
2. RESET only
3. STOP -> RESET
4. RESET -> STOP

Acceptance:
- clears only communication-loss class fault
- does not mask other faults
- does not cause unwanted start/run state issues

## C. Run state validation
Check whether:
- running bit can stay 1 while freq=0
- speed=0 and current=0 while running=1
- this must not be treated as actual pumping

## D. Flow command validation
For several targets:
- send target
- verify cmd_raw changes
- verify VFD freq/status changes
- hold for fixed time
- verify target remains stable
- stop and verify fallback to zero

## E. Integration next
After A-D:
- driver/backend normalization
- Klipper macros
- pause/fault policy
