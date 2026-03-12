# KNOWN_ISSUES.md

This file tracks confirmed defects, active constraints, and open checklist items in `drukmix`.

Nothing listed here should be silently dropped.
If an item exists in prior canonical project notes or README checklists and is still unresolved, it must remain tracked until explicitly verified as resolved or intentionally reclassified.

## Checklist maintenance rule

- add item only when confirmed;
- remove item only after explicit verification;
- do not silently rewrite history of defects;
- if an older item lacks detail, keep it as an open tracked item rather than losing it.

## Rules for this file

- Only confirmed defects, constraints, compatibility issues, or explicitly accepted active checklist items belong here.
- Do not remove an item only because code changed.
- Do not mark resolved until the fix is verified in practice.
- If an item changes meaning, update it explicitly instead of silently replacing it.
- If an item is architectural rather than bug-like, keep it tracked until its target state is actually established in canonical docs and implementation.

## Current confirmed defects

### 1. Moonraker compatibility for missing remote-method registration / subscription features remains a tracked issue

Status: active compatibility constraint

Moonraker compatibility handling is required for environments where some expected websocket/RPC features are unavailable or behave differently.

Startup may continue, but some remote DrukMix RPC behavior may still be compatibility-dependent.

Implication:

- startup success does not guarantee full remote RPC availability in every Moonraker build;
- Moonraker feature availability must be treated as compatibility-dependent, not assumed universal.

Related areas:

- Moonraker websocket connection
- remote method registration
- startup compatibility logic

## Active known issues and constraints

### 2. Zero-velocity / zero-flow semantics are sensitive and must not regress

Status: active constraint

The control path around zero target, zero velocity, and publish-time command handling is sensitive.

Recent fixes were required to make command application on publish behave correctly and to avoid incorrect stop behavior or zero-flow spam.

Implication:

- changes in command emission, print-state gating, debounce logic, or backend flow application must be reviewed against zero-target semantics;
- `zero` must not silently become `stop everything` unless that is the verified intended behavior for that specific layer.

Related areas:

- `drukmix_agent.py`
- backend command application
- print-state / publish logic

### 3. Pump offline handling and pause behavior are sensitive

Status: active constraint

Recent fixes were required to debounce pump offline pause behavior and avoid repeated or misleading pause-trigger behavior.

Implication:

- changes to offline detection, pause triggering, debounce, or fault episodes must be treated as high-risk;
- logs and runtime behavior must be checked together, not in isolation.

Related areas:

- `drukmix_agent.py`
- orchestration pause behavior
- pump connectivity / transport freshness handling

### 4. Telemetry truth must not be cosmetically improved into false certainty

Status: active architectural constraint

The project has already gone through corrections related to fake or misleading host telemetry semantics.

Fields must not be renamed or presented in a way that turns backend-reported values, command intent, transport freshness, or planned future demand into measured physical truth.

Implication:

- naming cleanup is dangerous if it changes semantic certainty;
- any telemetry refactor must be checked against canonical architecture and field-truth rules.

Related areas:

- backend-normalized status
- host-visible telemetry
- planner-derived host signals
- README / ARCHITECTURE semantic definitions

### 5. Deployment reality must stay aligned with canonical documented paths and roles

Status: active operational constraint

The project has already required fixes to restore canonical deployment behavior and helper logic.

Implication:

- deployment helpers, systemd assumptions, active config locations, log paths, and repository-run model must stay aligned with canonical docs;
- machine-side convenience changes must not silently redefine deployment reality.

Related areas:

- `tools/drukmix`
- `systemd/drukmix.service`
- `config_examples/`
- `~/printer_data/config`
- `~/printer_data/logs`

### 6. Bridge attachment currently depends on Linux udev alias strategy

Status: active operational constraint

The current normal runtime depends on `/dev/drukos-bridge` becoming available through Linux `udev` rules.

The installation flow is now more robust because it reloads rules and waits for the alias, but the project still depends on this Linux-specific mechanism.

Implication:

- transport attachment is currently operationally correct but not yet host-agnostic;
- portability to other Linux layouts or first-boot states still depends on explicit bridge-identification strategy.

Related areas:

- `tools/drukmix`
- udev rules
- serial attachment
- install / doctor flow

### 7. Bridge USB identity is still generic at the base USB-device level

Status: active device-identity constraint

The bridge is still seen by the host using a generic CP2102-style USB identity.

That is sufficient for current Linux + udev matching, but it is weaker than a clearly intentional project-level device identity.

Implication:

- device discovery is still partly dependent on host-side matching rules rather than explicit project-branded identity;
- multi-machine deployment and blank-device provisioning remain harder than they should be.

Related areas:

- bridge hardware
- USB identity
- udev matching
- install portability

### 8. Blank bridge/pump flashing and first-install provisioning are not yet canonicalized

Status: active provisioning constraint

The current installer supports the normal runtime/install path for already-known devices, but blank-device flashing and first-install provisioning are not yet part of one canonical documented flow.

Implication:

- steady-state install and first-time provisioning are not yet the same thing;
- future flashing/provisioning work must be documented explicitly and integrated intentionally.

Related areas:

- firmware flashing
- bridge provisioning
- pump-node provisioning
- install workflow

### 9. Planner-derived pump feedforward is not yet verified and must remain experimental

Status: active research constraint

Using Klipper planned extruder motion as an anticipatory pump-control input may materially improve concrete delivery timing, but it can also diverge from runtime truth during pause, fault, or queue-drain situations.

Implication:

- planned motion must not replace live-state gating;
- the available planner lead time must be measured on the actual machine;
- instrumentation should precede direct pump-control integration.

Related areas:

- Klipper trapq / motion report
- planner lead time
- DrukMix host orchestration
- experimental Klipper extra

## Active checklist

These items are intentionally preserved from the prior canonical checklist.
Some are architectural tasks rather than single-point bugs, but they remain open and must not be lost.

### 10. Normalize README so it stays the single source of truth for project overview, current deployment model, and active constraints

Status: active checklist item

README must stay aligned with the actual deployed model and must not drift behind working reality.

### 11. Remove accidental VFD-overfitting from canonical project description

Status: active checklist item

The project must stay multi-backend in its canonical description even if `pumpvfd` is the currently active field path.

### 12. Make backend boundaries explicit: generic host logic vs backend-specific logic

Status: active checklist item

Shared host logic and backend-specific behavior still need continued clarification and enforcement in both docs and implementation.

### 13. Define command ownership and status ownership by layer

Status: active checklist item

This has been partially documented, but it remains an active tracked item until fully reflected in architecture and code semantics.

### 14. Define field-truth categories for operator-visible status semantics

Status: active checklist item

Operator-visible status must stay explicitly classified by truth type and must not collapse different certainty levels into one ambiguous status surface.

### 15. Reconcile command success with telemetry truth

Status: active checklist item

Current system can physically run while normalized telemetry still reports zero applied output.

This mismatch remains a tracked issue until semantics and behavior are fully reconciled.

### 16. Audit bridge / pump status path for stale or delayed telemetry

Status: active checklist item

Status freshness and propagation path still need explicit audit.

### 17. Audit why `transport_link_ok` intermittently drops during otherwise idle/healthy operation

Status: active checklist item

Intermittent link-state drops remain tracked and must be investigated rather than normalized away.

### 18. Classify current operator-visible fields as `planned`, `requested`, `delivered`, `acknowledged`, `backend_reported`, `measured`, or `stale`

Status: active checklist item

This remains necessary to keep operator-visible semantics truth-preserving.

### 19. Separate requested target, delivered command, backend-reported output, and real physical output in naming and architecture

Status: active checklist item

This remains an active naming and architecture requirement.

### 20. Remove misleading host field `applied_pct` from the canonical host model

Status: active checklist item

Misleading host-visible fields must not remain canonical just because they are historically convenient.

### 21. Add rename / semantics clarification plan for misleading status fields

Status: active checklist item

Any rename effort must be planned, explicit, and truth-preserving.

### 22. Reduce unnecessary translation layers where the same command is reinterpreted multiple times

Status: active checklist item

Translation layers should be reduced only where meaning is preserved and ownership boundaries stay correct.

### 23. Instrument and measure planner lead time before adopting planner-derived pump feedforward

Status: active checklist item

The project needs measured evidence from the actual machine before planner-derived feedforward becomes canonical host behavior.
