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

### 1. `tools/drukos` install deploy path can conflict with active `.venv`

Status: open confirmed defect

The install/deploy path in `tools/drukos` needs to be fixed so runtime copy does not try to delete active `.venv` contents and spam `cannot delete non-empty directory` errors.

Implication:

- deploy helper behavior is not yet fully aligned with safe runtime deployment;
- deploy-path cleanup logic must be corrected without breaking canonical deployment workflow.

Related areas:

- `tools/drukos`
- deploy/install logic
- runtime copy behavior

### 2. Moonraker compatibility for missing `connection.register_remote_method` remains a tracked issue

Status: active compatibility constraint

Moonraker compatibility handling is required for environments where `connection.register_remote_method` is unavailable.

Startup may continue, but remote DrukMix RPC methods may be unavailable on Moonraker `v0.10.0-10-gfb257f8` / API `1.5.0`.

Implication:

- startup success does not guarantee full remote RPC availability;
- Moonraker feature availability must be treated as compatibility-dependent, not assumed universal.

Related areas:

- Moonraker websocket connection
- remote method registration
- startup compatibility logic

## Active known issues and constraints

### 3. Zero-velocity / zero-flow semantics are sensitive and must not regress

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

### 4. Pump offline handling and pause behavior are sensitive

Status: active constraint

Recent fixes were required to debounce pump offline pause behavior and avoid repeated or misleading pause-trigger behavior.

Implication:

- changes to offline detection, pause triggering, debounce, or fault episodes must be treated as high-risk;
- logs and runtime behavior must be checked together, not in isolation.

Related areas:

- `drukmix_agent.py`
- orchestration pause behavior
- pump connectivity / transport freshness handling

### 5. Telemetry truth must not be cosmetically improved into false certainty

Status: active architectural constraint

The project has already gone through corrections related to fake or misleading host telemetry semantics.

Fields must not be renamed or presented in a way that turns backend-reported values, command intent, or transport freshness into measured physical truth.

Implication:

- naming cleanup is dangerous if it changes semantic certainty;
- any telemetry refactor must be checked against canonical architecture and field-truth rules.

Related areas:

- backend-normalized status
- host-visible telemetry
- README / ARCHITECTURE semantic definitions

### 6. Deployment reality must stay aligned with canonical documented paths

Status: active operational constraint

The project has already required fixes to restore canonical deployment paths and helper behavior.

Implication:

- deployment helpers, runtime paths, systemd unit assumptions, and config locations must stay aligned with canonical docs;
- machine-side convenience changes must not silently redefine deployment reality.

Related areas:

- `tools/drukos`
- `systemd/drukmix.service`
- `/opt/drukmix`
- `/etc/drukmix`
- deployed macro/config paths

## Active checklist

These items are intentionally preserved from the prior canonical checklist.
Some are architectural tasks rather than single-point bugs, but they remain open and must not be lost.

### 7. Normalize README so it is the single source of truth for architecture, current state, and refactor constraints

Status: active checklist item

README still contains canonical substance that is being split into dedicated docs.
This normalization work is in progress and must finish without losing meaning.

### 8. Remove accidental VFD-overfitting from canonical project description

Status: active checklist item

The project must stay multi-backend in its canonical description even if `pumpvfd` is the currently active field path.

### 9. Make backend boundaries explicit: generic host logic vs backend-specific logic

Status: active checklist item

Shared host logic and backend-specific behavior still need continued clarification and enforcement in both docs and implementation.

### 10. Define command ownership and status ownership by layer

Status: active checklist item

This has been partially documented, but it remains an active tracked item until fully reflected in architecture and code semantics.

### 11. Define field-truth categories for operator-visible status semantics

Status: active checklist item

Operator-visible status must stay explicitly classified by truth type and must not collapse different certainty levels into one ambiguous status surface.

### 12. Reconcile command success with telemetry truth

Status: active checklist item

Current system can physically run while normalized telemetry still reports zero applied output.

This mismatch remains a tracked issue until semantics and behavior are fully reconciled.

### 13. Audit bridge / pump status path for stale or delayed telemetry

Status: active checklist item

Status freshness and propagation path still need explicit audit.

### 14. Audit why `transport_link_ok` intermittently drops during otherwise idle/healthy operation

Status: active checklist item

Intermittent link-state drops remain tracked and must be investigated rather than normalized away.

### 15. Classify current operator-visible fields as `requested`, `delivered`, `acknowledged`, `backend_reported`, `measured`, or `stale`

Status: active checklist item

This remains necessary to keep operator-visible semantics truth-preserving.

### 16. Separate requested target, delivered command, backend-reported output, and real physical output in naming and architecture

Status: active checklist item

This remains an active naming and architecture requirement.

### 17. Remove misleading host field `applied_pct` from the canonical host model

Status: active checklist item

Misleading host-visible fields must not remain canonical just because they are historically convenient.

### 18. Add rename / semantics clarification plan for misleading status fields

Status: active checklist item

Any rename effort must be planned, explicit, and truth-preserving.

### 19. Reduce unnecessary translation layers where the same command is reinterpreted multiple times

Status: active checklist item

Translation layers should be reduced only where meaning is preserved and ownership boundaries stay correct.

### 20. Separate AUTO motion-derived commands from operator commands in architecture and naming

Status: active checklist item

AUTO-derived control and operator-issued control must not be semantically collapsed.

### 21. Preserve working Err16 behavior while simplifying architecture

Status: active checklist item

Architecture cleanup must not regress currently working Err16 handling.

### 22. Preserve TPL-specific stop semantics while simplifying architecture

Status: active checklist item

Simplification must not destroy backend-specific safety-critical stop semantics.

### 23. Define refactor order that does not require rediscovering backend-specific safety rules

Status: active checklist item

Refactor sequencing must preserve already learned backend safety knowledge instead of forcing rediscovery.


### 24. Reduce deployment dependence on fixed user/path assumptions

Status: active checklist item

Current deployment is still tied to the existing `drukos`-style layout, fixed paths, and at least some user/path assumptions.

This must remain explicit until portability is intentionally implemented and verified.

### 25. Document real operating assumptions explicitly in README

Status: active checklist item

README should state the real expected operating environment clearly, including Klipper, Moonraker, Mainsail, separate `drukmix` service, and the current canonical deployment layout.

The project should not present itself as portable or generic beyond what is actually verified.

## Resolution policy

An item may be marked resolved only when:

1. a fix or canonical replacement exists in repo;
2. deployment used canonical workflow;
3. runtime or documentation behavior was verified as appropriate to the item;
4. the issue, mismatch, or checklist target is no longer open.

Until then, keep the item listed.
