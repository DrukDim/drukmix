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

- `drukmix_driver.py`
- backend command application
- controller-to-backend command application

### 3. Pump offline handling and pause behavior are sensitive

Status: active constraint

Recent fixes were required to debounce pump offline pause behavior and avoid repeated or misleading pause-trigger behavior.

Confirmed current findings:
- repository code had drifted from a printer-side experimental fix, so planner lookahead was still using point-sampled horizon selection instead of window-max selection inside the requested lookahead window;
- repository code used `bridge_offline_timeout_s` for the elapsed-offline pause path where `pump_offline_timeout_s` was expected for pump-offline decision timing.

Implication:

- changes to offline detection, pause triggering, debounce, or fault episodes must be treated as high-risk;
- logs and runtime behavior must be checked together, not in isolation;
- repository and deployed runtime must be re-synchronized before further pump-offline tuning conclusions are accepted.

Related areas:

- `drukmix_driver.py`
- orchestration fail-safe behavior
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

### 5a. Upstream `mainsail.cfg` default pause/cancel park behavior conflicts with required machine semantics

Status: active compatibility constraint with managed mitigation

Upstream `mainsail.cfg` parks the toolhead during `PAUSE` and may also park during `CANCEL_PRINT`.
That conflicts with the required concrete-printer behavior here: pause must finish buffered motion and stop in place, and cancel must not inject an automatic park move.

Confirmed current rule:
- helpers should detect the standard upstream park lines and remove them idempotently during install/update/reset;
- if `mainsail.cfg` is already fixed or customized in some other equivalent way, helpers should leave it unchanged.

Implication:

- updates to `mainsail-config` can silently restore upstream park behavior unless the helper re-normalizes it;
- pause/cancel behavior should be re-verified after printer-stack updates.

Related areas:

- `tools/drukmix`
- `~/printer_data/config/mainsail.cfg`

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

### 8a. CP2102 USB identity is not unique between bridge and pump provisioning devices

Status: active provisioning and attachment constraint

Current ESP provisioning devices use CP2102 USB-UART bridges that can present the same generic USB identity to Linux.

Confirmed current finding:
- relying on CP2102 generic serial identity such as `serial=0001` is not sufficient to distinguish bridge from pump programming adapters;
- this can make `/dev/drukos-bridge` ambiguous if the alias is matched only by generic CP2102 identity;
- a proper long-term fix likely requires an explicit CP2102 provisioning stage with unique programmed USB identity, rather than relying on ESP firmware flash alone.

Implication:

- bridge attachment and first-install provisioning must not assume CP2102 USB identity is globally unique out of the box;
- any stable bridge alias strategy must either bind to an explicitly verified physical port or use a future canonical CP2102 identity-provisioning workflow;
- USB identity provisioning is deferred work and must not be silently treated as already solved.

Related areas:

- bridge USB aliasing
- first-install provisioning
- CP2102 EEPROM / identity programming
- `tools/drukmix`

### 9. Planner-authoritative pump control is validated as the intended direction, but migration is incomplete

Status: active migration constraint

Planner-derived extruder demand from `drukmix_planner_probe` has been validated as the intended printer-side motion authority for automatic pump control.

However, the host runtime path still contains transition-era dependencies and semantics that must be removed or formalized.

Implication:

- mixed authority between planner demand and Moonraker lifecycle/motion fields must not remain indefinitely;
- final planner-only control semantics, planner freshness handling, and lookahead policy still need explicit canonicalization.

Related areas:

- `drukmix_driver.py`
- `klipper_extra/drukmix_planner_probe.py`
- `klipper_extra/drukmix_controller.py`
- planner lookahead policy
- host orchestration semantics


### 9a. Planner/controller observability can disagree with observed machine behavior during live print

Status: active confirmed observability defect

`drukmix_planner_probe` and controller status surfaces have produced live sessions where planned queue/velocity or controller state appeared inactive or null, while the real machine still showed automatic pump behavior such as `prestart`.

Implication:

- the current confirmed problem is not that automatic planner-authoritative pumping is categorically broken;
- the confirmed problem is that planner/controller observability is not yet fully trustworthy in all live sessions;
- investigation must check the full path: extruder hook -> mirrored move queue -> probe status -> Moonraker status delivery -> host-side status observation.

Related areas:

- `klipper_extra/drukmix_planner_probe.py`
- `klipper_extra/drukmix_controller.py`
- Moonraker status transport
- planner timebase / queue mirroring

### 9b. Research-style multi-horizon planner payload is still present in the runtime control path

Status: active migration defect

The runtime production path still contains `PLANNER_HORIZONS`, `planned_v_*`, and host-side planner horizon selection logic.

Implication:
- research instrumentation is still leaking into production control semantics;
- host orchestration still depends on a non-canonical planner payload shape;
- production contract cleanup must remove multi-horizon payload from the normal production runtime path.

Related areas:
- `klipper_extra/drukmix_planner_probe.py`
- `klipper_extra/drukmix_controller.py`

### 9c. Backend mode `UNKNOWN` must block automatic orchestration until explicit mode integration is complete

Status: active safety constraint

`UNKNOWN` is not equivalent to `MANUAL`, but it is also not acceptable for automatic production pumping.

Implication:
- automatic pump orchestration must be blocked in `UNKNOWN`;
- current deployment-stage expectation is `AUTO` operation until physical mode switching is intentionally integrated;
- future MANUAL/AUTO selector support must be added explicitly, not by weakening `UNKNOWN` handling.

Related areas:
- backend-normalized status
- `drukmix_driver.py`
- runtime pause/safety logic

### 9d. Operator flush/reverse override can remain logically active while backend-reported `running` stays false

Status: active confirmed defect

Verified on `duet` on 2026-03-26:
- `DRUKMIX_FLUSH PCT=100 DURATION=0` now remains active until explicit `DRUKMIX_STOP`;
- `DRUKMIX_REVERS PCT=100 DURATION=0` also remains active until explicit `DRUKMIX_STOP`;
- `DRUKMIX_STATUS` correctly shows `flush=1`, `flush_pct=100.0%`, and `flush_rev=0/1` during the active operator override;
- at the same time, backend-reported status still showed `mode=AUTO`, `link_ok=1`, `fault=0`, and `running=0`.

Implication:
- the macro/driver operator contract is working, but lower execution truth is still unresolved;
- this must not be described as proven physical non-rotation, because there is currently no measured RPM/flow feedback in the canonical host status path;
- the unresolved boundary is below operator-command acceptance and above measured physical truth, likely in bridge command application, pump-node/VFD interaction, or backend-reported status semantics.

Related areas:
- `drukmix_driver.py`
- `backend/backend_pumpvfd.py`
- `backend/bridge_usb_transport.py`
- bridge / pump-node status semantics
- operator override verification

## Active checklist

These items are intentionally preserved from the prior canonical checklist.
Some are architectural tasks rather than single-point bugs, but they remain open and must not be lost.

### 10. Runtime path still depends on non-canonical Moonraker lifecycle/motion fields during planner migration

Status: active migration item

Automatic pump control should no longer depend on `motion_report.live_extruder_velocity`, `print_stats.state`, `pause_resume`, `idle_timeout`, or `webhooks` once planner-authoritative orchestration is adopted.

### 11. Planner freshness / staleness guardrail is not yet canonicalized

Status: active control-safety item

Planner-authoritative control requires an explicit rule for when planner data is considered stale and automatic pumping must fail safe.

### 12. Cold-start / run / stop lookahead policy is not yet fully formalized

Status: active control-policy item

The system now needs a canonical multi-phase lookahead policy:
- longer cold-start lookahead,
- shorter running lookahead,
- longer stop lookahead.

Additional current note:
- point-sampled lookahead selection was confirmed insufficient on the live machine and repository runtime must use window-max selection across the active lookahead window before policy conclusions are treated as stable.

### 13. Normalize README so it stays the single source of truth for project overview, current deployment model, and active constraints

Status: active checklist item

README must stay aligned with the actual deployed model and must not drift behind working reality.

### 14. Remove accidental VFD-overfitting from canonical project description

Status: active checklist item

The project must stay multi-backend in its canonical description even if `pumpvfd` is the currently active field path.

### 15. Make backend boundaries and layer ownership explicit

Status: active checklist item

Shared host logic, backend-specific behavior, and command/status ownership by layer still need continued clarification and enforcement in both docs and implementation.

### 16. Define operator-visible status truth categories and truth-preserving naming

Status: active checklist item

Operator-visible status must stay explicitly classified by truth type and must not collapse different certainty levels into one ambiguous status surface.

This includes:
- classifying fields as `planned`, `requested`, `delivered`, `acknowledged`, `backend_reported`, `measured`, or `stale`;
- separating requested target, delivered command, backend-reported output, and real physical output in naming and architecture;
- removing misleading host-visible fields such as `applied_pct` from the canonical host model;
- keeping any rename / semantics clarification effort explicit and truth-preserving.

### 17. Reconcile telemetry truth with command success and stale propagation

Status: active checklist item

Current system can physically run while normalized telemetry still reports zero applied output.

This mismatch remains tracked until semantics and behavior are fully reconciled, including audit of stale or delayed bridge / pump status propagation.

### 18. Audit why `transport_link_ok` intermittently drops during otherwise idle/healthy operation

Status: active checklist item

Intermittent link-state drops remain tracked and must be investigated rather than normalized away.

### 19. Reduce unnecessary translation layers where the same command is reinterpreted multiple times

Status: active checklist item

Translation layers should be reduced only where meaning is preserved and ownership boundaries stay correct.

### 20. Instrument and measure planner lead time before adopting planner-derived pump feedforward

Status: active checklist item

The project needs measured evidence from the actual machine before planner-derived feedforward becomes canonical host behavior.

### 21. Validate the canonical variability model against at least one additional clean machine bring-up

Status: active architecture/workflow item

The project now defines canonical variation classes for:

- core;
- environment-specific;
- machine-specific;
- backend-specific;
- compatibility-specific.

That model still needs validation against at least one additional clean installation / new-printer bring-up before a final profile or folder-layout strategy is treated as settled project truth.

Implication:

- the variability model is now documented and canonical as a rule set;
- the final concrete profile/folder layout should remain conservative until validated by real second-machine experience;
- new bring-up work must report which differences were truly machine-specific, backend-specific, environment-specific, or compatibility-specific.
