# WORKFLOW.md

This file defines the canonical working procedure for changing, deploying, and verifying `drukmix`.

Until explicitly replaced by a newer canonical rule, this workflow is mandatory.

## Core workflow

Canonical workflow:

`repo -> deploy -> restart -> verify`

This means:

1. Make changes in the repository first.
2. Deploy repository state to the target machine.
3. Restart the affected service(s).
4. Verify actual runtime behavior on the machine.

Do not treat printer-side edits as canonical source of truth.

## Source of truth rules

Canonical source of truth is the repository.

Rules:

- deployment must be performed from committed repo state, not from ad hoc manual edits on the printer;
- the repository checkout is the canonical executable source;
- live files under `~/printer_data/config` are machine-side active files, but not automatically the canonical authoring source;
- printer-side changes are not canonical until committed back into the repository;
- quick fixes made directly on the machine must be treated as temporary only.

If runtime state and repo state diverge, repo state must be updated or the runtime change must be discarded.

## Canonical deployment layout

Current canonical deployment layout:

- source repo: `/home/drukos/drukmix`
- systemd unit: `/etc/systemd/system/drukmix.service`
- active driver config file: `/home/drukos/printer_data/config/drukmix_driver.cfg`
- active controller config file: `/home/drukos/printer_data/config/drukmix_controller.cfg`
- active macros file: `/home/drukos/printer_data/config/drukmix_macros.cfg`
- active printer config: `/home/drukos/printer_data/config/printer.cfg`
- runtime log: `/home/drukos/printer_data/logs/drukmix_driver.log`
- template/default config files in repo:
  - `config_examples/drukmix_driver.cfg`
  - `config_examples/drukmix_controller.cfg`
  - `config_examples/drukmix_macros.cfg`

These paths and roles must not be changed casually.
If changed, the new layout must be reflected in canonical docs.

## Normal install/update model

Current normal repository-driven deployment model is:

1. clone or update repo checkout;
2. run `./tools/drukmix install` or `./tools/drukmix update`;
3. let the helper:
   - create/update `.venv`;
   - install Python dependencies;
   - install the systemd unit;
   - install default live driver/controller config and macros only if missing;
   - patch live config paths if needed;
   - migrate legacy DrukMix macro files that still advertise unsupported remote methods;
   - ensure `[include drukmix_controller.cfg]` exists in `printer.cfg`;
   - ensure `[include drukmix_macros.cfg]` exists in `printer.cfg`;
   - install bridge udev rule;
   - reload udev rules;
   - wait for `/dev/drukos-bridge`;
   - install the experimental Klipper extra if the expected Klipper tree exists;
   - restart the service;
4. verify runtime behavior.

## Temporary research-branch workflow

A temporary research branch may add experimental instrumentation that is not yet canonical production behavior.

Rules for such branches:

- the branch must state clearly that the work is experimental;
- the experiment must preserve truth labels and safety gates;
- instrumentation should be preferred before direct behavior changes;
- installer changes for experimental extras should be safe, explicit, and low-risk;
- experimental config/includes must also be repo-driven and reproducible;
- experimental deployment must not silently redefine the canonical production model.

## New printer bring-up workflow

A new printer must be brought up against the canonical core baseline first.

Required order:

1. Install the canonical repository-driven baseline.
2. Verify what works without local overrides.
3. Record only confirmed machine-specific differences.
4. Add environment-specific, machine-specific, backend-specific, or compatibility-specific overrides explicitly.
5. Do not modify core for a problem that is local to one machine.
6. If a local issue reveals a real core defect, classify it explicitly as a core defect before changing core.

Rules:

- do not create a new repository structure for one printer as an ad hoc shortcut;
- do not mix machine-specific, backend-specific, and environment-specific changes into one undifferentiated “printer variant”;
- keep new-printer bring-up aligned with the canonical variability model in `VARIABILITY_MODEL.md`.

## Change procedure

For normal changes:

1. Inspect current canonical docs first:
   - `README.md`
   - `AGENTS.md`
   - `WORKFLOW.md`
   - other canonical docs if present
2. Make the smallest change that solves the problem.
3. Commit the change in repo.
4. Deploy to target machine using the repository-driven path.
5. Restart the relevant service(s).
6. Verify actual behavior, not just successful file copy or clean logs.
7. If machine-side adjustment was needed during verification, commit the final truth back into repo.

## Verification rules

Verification must be tied to real machine semantics.

Examples of acceptable verification:

- service starts correctly;
- `./tools/drukmix doctor` shows expected files and expected bridge alias state;
- `/dev/drukos-bridge` exists and resolves to the intended serial device;
- expected command path works end-to-end;
- observed runtime behavior matches intended control semantics;
- telemetry meaning is still truthful;
- fault handling still behaves as documented.

For planner-authoritative changes, verification must include:

- automatic target generation works without depending on `motion_report.live_extruder_velocity`;
- automatic pump run/stop behavior follows planner-derived demand rather than printer lifecycle state;
- planner staleness fails safe;
- backend fault/manual/offline reactions still work;
- flush / operator override behavior still works;
- logs make clear which values are planned-demand values and which are backend/device truth.

For experimental planner instrumentation, acceptable verification also includes:
- the experimental Klipper extra is installed at the expected location;
- Klipper loads the extra without breaking printer startup;
- planner-derived signals can be read and compared against live extruder velocity;
- research logs make clear which values are planned, live, requested, or backend-reported.

Examples of insufficient verification:

- "code looks cleaner";
- "service restarted without error";
- "field names look nicer";
- "UI appears plausible" without checking machine truth.

## Bridge and device attachment rules

Current normal runtime depends on a stable Linux bridge alias:

`/dev/drukos-bridge`

Rules:

- service restart should happen only after the expected bridge alias is present or an explicit warning is emitted;
- bridge attachment must be verified during install/doctor flows;
- generic host-visible USB naming must not be treated as a durable canonical identity model;
- future first-install / blank-device provisioning must be documented explicitly when it becomes canonical.

## Debugging rules

When debugging:

- prefer targeted changes over broad rewrites;
- preserve field truth semantics;
- do not hide unresolved behavior behind documentation wording;
- do not silently redefine ownership boundaries between host, backend, transport, and device;
- record confirmed issues in canonical docs.

## Documentation rules

When workflow changes:

- update `README.md` if the workflow change becomes canonical;
- update `WORKFLOW.md` with the operational procedure;
- update `VARIABILITY_MODEL.md` if the change alters allowed variation classes or non-mixing rules;
- keep `AGENTS.md` aligned if the agent-facing rules changed.

## Default stance

If there is a conflict between:
- fast temporary machine-side editing, and
- repository-driven reproducible workflow,

choose repository-driven reproducible workflow.
