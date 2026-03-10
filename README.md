# DrukMix

DrukMix is a control stack for a concrete 3D printing system built around Klipper, Moonraker, Mainsail, and external pump/mixer hardware.

This project is **not** a plastic FDM workflow.
It is for a concrete extrusion machine with:
- screw extruder
- screw pump feeding material through a hose
- external pump driver hardware
- custom host and firmware control logic

---

## Single source of truth rule

This `README.md` is the canonical project document.

Rules:
- all confirmed architectural decisions must be reflected here;
- all confirmed defects / refactor items must be tracked here;
- other `docs/*.md` files are supporting references only;
- if some rule exists in another markdown file but is not reflected here, it is not yet canonical.

This file must distinguish clearly between:
- **current verified state**
- **target architecture**
- **confirmed defects**
- **refactor constraints**

---

## Project scope

The system must support more than one physical pump backend.

Current backend families:
- `pumpvfd` — VFD-driven pump
- `pumptpl` — analog / potentiometer / relay style pump control

Future hardware may be added, but upper layers must not become hardcoded to one backend family.

---

## Current verified state

### Host stack
Current host stack:
- Klipper
- Moonraker
- Mainsail
- separate `drukmix` agent service

### Current deployed backend
Current deployed field path is `pumpvfd`.

### Current host control path
Current host control chain is:

`Klipper macro -> Moonraker remote method -> DrukMix agent -> backend -> bridge USB protocol -> ESP-NOW bridge -> pump node -> hardware driver`

This path currently works, but is too layered and harder to reason about than desired.

### Current observed issue
Recent live logs show:
- intermittent `transport_link_ok=0`
- repeated `status_age_ms` spikes around offline threshold
- command path works enough to run/stop the pump
- telemetry / command acknowledgement shape is still more fragile than desired

### Current observed mismatch
During manual run testing:
- run command reaches the pump
- pump physically runs
- host-visible flow output telemetry was previously modeled too optimistically
- current host model no longer exposes fake measured-flow style fields

This means command delivery and telemetry truth are not yet equivalent.

---

## Target architecture

The target architecture is:

### 1. Host orchestration layer
Responsible for:
- print-state integration
- flow computation from print motion
- flush / prime orchestration
- UI-facing status and operator commands
- policy decisions such as pause-on-fault / pause-on-offline

Must **not** contain backend-specific electrical or transport hacks.

### 2. Backend adapter layer
Responsible for:
- translating abstract host pump commands into backend-specific actions
- exposing normalized pump status upward
- owning backend-specific stop/reset/manual semantics

This is the layer where `pumpvfd` and `pumptpl` are allowed to differ.

### 3. Transport layer
Responsible for:
- message delivery
- retries / timeout handling
- raw transport status
- no print business logic

### 4. Device node layer
Responsible for:
- hardware I/O
- local/manual mode detection
- safe command execution
- backend-local fault/reset behavior
- reporting backend state upward

---

## Canonical invariants

These rules must stay true across refactors.

### Invariant 1 — abstract pump model first
Upper layers must talk to one logical pump model, not to a VFD-specific or TPL-specific model.

### Invariant 2 — backend semantics stay backend-local
Examples:
- VFD fault reset timing
- TPL stop by relay + potentiometer to zero
- local/manual selector behavior
- hardware-safe stop sequence

These must stay in backend/node logic, not in generic host orchestration.

### Invariant 3 — transport must not own print policy
Bridge / transport must not own:
- print pause policy
- flush policy
- slicer semantics
- minimum flow logic
- print state logic

### Invariant 4 — telemetry must represent reality
A command is not enough.
The system must distinguish between:
- requested target
- delivered command
- actual device-reported state

Current project constraint:
- there is currently no encoder, flowmeter, or pressure-based delivered-flow measurement in the deployed system;
- host-visible telemetry must not claim measured real output where no real sensor exists;
- placeholder or derived fields that look like measured delivered flow must not be added to the canonical host model.

### Invariant 5 — no permanent VFD bias in canonical model
The canonical model must not assume:
- Modbus-only reset
- VFD-only fault fields
- VFD-only stop semantics
- VFD-only telemetry fields

### Invariant 6 — no hidden behavior outside README
If a project rule matters for development decisions, it must be written here.

---

## Canonical control model

Upper layers should think in these concepts:

- set flow target
- stop
- reset fault
- read normalized status
- detect local/manual mode
- detect offline / stale telemetry
- detect backend faulted state

The canonical model is about behavior, not about one specific wire protocol.


### Command ownership model

The system must distinguish command ownership by layer.

#### 1. Operator intent
Examples:
- stop
- reset fault
- flush
- gain / limits / calibration-style commands

These commands originate from macros / remote methods / operator actions.

#### 2. Host orchestration command
For AUTO pumping, host orchestration computes an abstract motion-derived command from print state.

Current computed fields in host core are:
- `target_pct`
- `rev`
- `stop`
- `reason`

This layer owns print-driven intent, not backend transport details.

#### 3. Backend command
Backend adapter translates abstract host command into backend-specific action.

Examples:
- `pumpvfd`: run/stop/reset over VFD path
- `pumptpl`: relay / potentiometer / backend-specific safe stop sequence

#### 4. Transport command
Transport layer converts backend command into delivery packets / frames / retries.

This layer owns:
- packet type
- sequence / acknowledgement transport
- CRC / framing
- link retry behavior

This layer must not reinterpret print intent.

#### 5. Device action
Device node performs hardware action and reports device-side state.

### Status ownership model

The system must distinguish status ownership by layer.

#### 1. Device fact
Raw device/backend fact reported by node or hardware-facing firmware.

Examples:
- fault code
- running bit
- reported_target_milli_lpm
- reported_output_milli_lpm
- hw_setpoint_raw
- pump_flags

#### 2. Transport status
Bridge/transport-visible status about delivery and freshness.

Examples:
- `transport_link_ok`
- `last_ack_seq`
- `retry_count`
- `send_fail_count`
- `status_age_ms`
- transport-visible stale/offline condition

#### 3. Backend-normalized status
Backend adapter converts raw transport/device state into normalized backend status.

This is where:
- backend fault mapping
- manual/remote interpretation
- normalized running/fault/manual/offline state
belong.

#### 4. Host orchestration context
Host combines normalized backend status with print context.

Examples:
- printing / paused / idle state
- extrude factor
- live extruder velocity
- pause-on-fault policy
- pause-on-offline policy

#### 5. UI/operator status
Final operator-visible state shown in logs / notifications / UI.

This layer may summarize lower layers, but must not destroy field meaning.

### Field truth rule

Every important status field must be classified explicitly as one of:

- `requested`
- `delivered`
- `acknowledged`
- `backend_reported`
- `measured`
- `stale`

The current architecture must not use one field as a silent substitute for another.

### Current confirmed semantic mismatch

The current `pumpvfd` path already shows a field-truth mismatch:

- backend keeps `target_pct` as last requested target;
- there is currently no independent host-visible measured-flow field;
- physical pump motion and command delivery must not be confused with measured delivered flow.

Therefore current telemetry does not yet cleanly distinguish:
- requested target
- delivered backend command
- actual backend-reported output
- real physical output

This mismatch must be resolved before architecture simplification touches status semantics.

### Current confirmed simplification target

The main simplification target is not “remove layers blindly”.

It is:
- remove duplicate reinterpretation of the same command;
- remove duplicate reinterpretation of the same status;
- keep exactly one owner for each meaning;
- preserve backend-local safety semantics while reducing translation count.


### Current field classification snapshot

Current field classification for the active `pumpvfd` path:

#### Host-orchestration requested
- `CoreOutput.target_pct`
- `CoreOutput.rev`
- `CoreOutput.stop`
- `CoreOutput.reason`
- `PumpVfdBackend._last_target_pct`
- `PumpStatus.target_pct`

Meaning:
- host-requested command intent
- not proof of delivery
- not proof of backend application
- not proof of physical output

#### Transport delivery / acknowledgement
- outgoing `USB_SET_FLOW(cmd_target_milli_lpm, flags)`
- `last_ack_seq`
- `retry_count`
- `send_fail_count`
- `seq_reply`

Meaning:
- transport-layer delivery / acknowledgement state
- not direct proof of backend-reported output
- not physical output

#### Freshness / stale / link state
- `transport_link_ok`
- `status_age_ms`
- cached status presence / absence

Meaning:
- freshness and communication visibility
- not pump-flow truth

#### Backend-reported device state
- `fault_code`
- `pump_state`
- `pump_online`
- `reported_running`
- `rev_active`
- `control_mode`
- `reported_target_milli_lpm`
- `hw_setpoint_raw`
- `pump_flags`
- `applied_code`
- `pump_max_milli_lpm`

Meaning:
- device/backend-reported state or backend-normalized device state
- may still differ from real physical output

#### Backend-reported derived field

Meaning:
- currently not exposed in the canonical host model because there is no independent delivered-flow sensor
- not measured physical output
- must not be treated as proof that the pump is or is not physically moving

### Current missing truth layer

The current active path does not expose a separate canonical field for:
- real physical output confirmation
- measured screw/pump motion
- independently measured delivered flow

Therefore current architecture must not treat:
- `target_pct`
- `last_ack_seq`
- `reported_running`

as interchangeable truth.


### Rename / semantics clarification plan

This plan is for naming cleanup only.
It must preserve current behavior until each rename is implemented and verified.

#### 1. measured delivered flow telemetry
Current owner:
- transport/backend-derived field

Current truth class:
- `backend_reported` derived field

Current source:
- currently not exposed in the canonical host model because there is no independent delivered-flow sensor

Problem:
- name sounds like “command was applied”
- can be misread as physical-output truth
- can be misread as delivery confirmation

Target direction:
- rename to one of:
    - `derived_output_pct`
  - `backend_output_pct`

Rule:
- new name must explicitly imply derived/backend-reported meaning
- must not imply measured physical output
- must not imply delivery acknowledgement

#### 2. `target_pct`
Current owner:
- host orchestration / backend wrapper

Current truth class:
- `requested`

Current source:
- `CoreOutput.target_pct`
- `PumpVfdBackend._last_target_pct`
- `PumpStatus.target_pct`

Problem:
- current name is short but not explicit enough in operator/debug context
- can be confused with delivered or applied backend command

Target direction:
- keep internal short form if needed
- operator/debug-facing naming should move toward:
  - `requested_target_pct`
  - or `host_target_pct`

Rule:
- this field means requested host intent only
- it is not delivery proof
- it is not backend-applied proof
- it is not physical-output proof

#### 3. `running`
Current owner:
- backend-normalized status using device/backend input

Current truth class:
- `backend_reported`

Current source:
- currently sourced from backend/device status path

Problem:
- name is too broad
- can be misread as physical pumping truth
- can be misread as operator-visible “material is flowing”

Target direction:
- split or rename depending on final model:
  - `backend_running`
  - `reported_running`
  - `device_running_state`

Rule:
- if this field remains singular, its meaning must be fixed explicitly
- it must not silently mean physical-output confirmation

#### 4. `transport_link_ok`
Current owner:
- transport status

Current truth class:
- `stale` / freshness / communication visibility

Problem:
- can be over-read as “pump state is valid”
- can be confused with backend-online truth

Target direction:
- keep if convenient, but document clearly as transport visibility only
- possible future explicit names:
  - `transport_link_ok`
  - `status_link_ok`

Rule:
- this field says communication visibility/freshness only
- it does not prove pump stop/run/output truth

#### 5. `status_age_ms`
Current owner:
- transport freshness status

Current truth class:
- `stale`

Problem:
- currently useful, but easy to ignore semantically
- without naming context it can be mixed into device truth

Target direction:
- keep or rename to:
  - `status_age_ms`
  - `transport_status_age_ms`

Rule:
- this field describes status freshness only
- it is not a flow/output/device-actuation field

#### 6. `reported_target_milli_lpm`
Current owner:
- backend/device-reported state

Current truth class:
- `backend_reported`

Problem:
- can be confused with host-requested flow target
- transport/backend/device layers may each mean different “target”

Target direction:
- distinguish clearly from host intent:
  - `backend_reported_target_milli_lpm`
  - or `reported_reported_target_milli_lpm`

Rule:
- if host also owns target-flow naming, host and backend names must not collide semantically

#### 7. delivered flow telemetry
Current owner:
- backend/device-reported state

Current truth class:
- `backend_reported`

Problem:
- word `actual` sounds stronger than current proof level
- may still be reported/estimated device value, not independently measured real output

Target direction:
- rename toward:
    - `backend_output_milli_lpm`

Rule:
- unless there is an independent sensor, this field must not imply physical measured truth

#### 8. `hw_setpoint_raw`
Current owner:
- backend/device-reported state

Current truth class:
- `backend_reported`

Problem:
- name is debug-like but acceptable
- meaning should stay clearly backend/device-local

Target direction:
- keep as backend/debug field unless a better backend-neutral raw-actuation name appears

Rule:
- do not surface this as canonical physical-output truth

### Rename rollout rule

Renames must be implemented in this order:

1. document field meaning in README
2. rename backend/internal fields
3. rename operator-visible/log fields
4. verify no old meaning leaks through logs/UI/macros
5. only then remove legacy aliases if any are used temporarily

### Minimum first rename target

The first rename target should be:

- `applied_pct` was removed from the host model because it implied false measured-output semantics

Reason:
- it is currently the most misleading field name
- it directly collides with field-truth rules already documented above

---

## Backend matrix

### `pumpvfd`
Nature:
- remote-controlled VFD backend
- currently active deployment path

Important backend-local semantics:
- fault reset behavior matters;
- Err16 handling matters;
- status currently includes VFD-related fault mapping;
- command path works, but telemetry truth still needs work.

### `pumptpl`
Nature:
- analog / digital potentiometer + relay style backend

Important backend-local semantics:
- stop is backend-specific;
- safe stop may require relay action and setpoint-to-zero sequence;
- VFD-style reset semantics do **not** automatically apply;
- VFD assumptions must not leak into TPL logic.

### Future backends
Any future backend must implement the same abstract host-visible model, while keeping its low-level semantics local to the backend.

---

## Manual / local override rule

Manual / local override is first-class system state.

Rules:
- if local/manual mode is active, remote motion commands must not be treated as normal accepted control;
- local/manual state must be visible in normalized status;
- host must treat backend as not fully remotely controllable until the condition clears;
- exact implementation may differ by backend.

This rule applies both to:
- VFD selector / local mode cases
- TPL or future hardware local override designs

---

## Current confirmed defects / checklist

Only confirmed items belong here.

### Active checklist

- [x] Normalize README so it is the single source of truth for architecture, current state, and refactor constraints.
- [x] Remove accidental VFD-overfitting from canonical project description.
- [x] Make backend boundaries explicit: generic host logic vs backend-specific logic.
- [x] Define command ownership and status ownership by layer.
- [x] Define field-truth categories for operator-visible status semantics.
- [ ] Reconcile command success with telemetry truth; current system can physically run while normalized telemetry still reports zero applied output.
- [ ] Audit bridge / pump status path for stale or delayed telemetry.
- [ ] Audit why `transport_link_ok` intermittently drops during otherwise idle/healthy operation.
- [ ] Classify current operator-visible fields as `requested`, `delivered`, `acknowledged`, `backend_reported`, `measured`, or `stale`.
- [ ] Separate requested target, delivered command, backend-reported output, and real physical output in naming and architecture.
- [x] Remove misleading host field `applied_pct` from the canonical host model.
- [ ] Add rename/semantics clarification plan for misleading status fields.
- [ ] Reduce unnecessary translation layers where the same command is reinterpreted multiple times.
- [ ] Separate AUTO motion-derived commands from operator commands in architecture and naming.
- [ ] Preserve working Err16 behavior while simplifying architecture.
- [ ] Preserve TPL-specific stop semantics while simplifying architecture.
- [ ] Define refactor order that does not require rediscovering backend-specific safety rules.

### Checklist maintenance rule
- add item only when confirmed;
- remove item only after explicit verification;
- do not silently rewrite history of defects.

---

## Refactor guardrails

Refactor is allowed only under these constraints.

### Guardrail 1 — do not break working fault behavior
Especially:
- Err16 reset path
- current VFD fault mapping behavior

### Guardrail 2 — do not generalize by deleting backend semantics
Abstraction must keep:
- `pumpvfd`-specific safe behavior
- `pumptpl`-specific safe behavior

### Guardrail 3 — simplify by removing duplicate interpretation layers
Preferred direction:
- fewer command translations
- fewer duplicated status meanings
- clearer ownership per layer

### Guardrail 4 — preserve field truth
For any status field, define exactly whether it means:
- requested
- acknowledged
- last delivered
- actual measured / reported
- stale cached

### Guardrail 5 — refactor in safe order
Safe order:
1. freeze canonical README rules
2. define ownership and naming
3. identify redundant layers
4. only then change code paths

---

## Desired next architecture review outcome

The next architecture review must produce:

- one canonical flow of command ownership;
- one canonical flow of status ownership;
- one backend-neutral host model;
- backend-local low-level semantics for VFD / TPL;
- explicit naming for requested vs actual vs stale status;
- explicit list of layers that can be removed or merged safely.

No code simplification should happen before this reasoning is written and agreed here.

---

## Docs map

Supporting docs remain useful, but are secondary to this README.

### VFD references
- `docs/vfd/README.md`
- `docs/vfd/m900_m980_shared_semantics.md`
- `docs/vfd/m900_m980_differences.md`
- `docs/vfd/m900_m980_faults.md`
- `docs/vfd/modbus_driver_contract.md`
- `docs/vfd/test_plan_next.md`
- `docs/vfd_faults.md`

These documents provide detailed backend reference material.
They do **not** replace the canonical rules in this README.

---

## Practical project rule

Any future proposal must answer three questions before code changes start:

1. What belongs to generic host logic?
2. What belongs only to a backend?
3. What evidence shows a layer is truly redundant rather than just temporarily inconvenient?

If that is not written clearly, the change is not ready.
