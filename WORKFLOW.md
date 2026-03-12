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
- active config file: `/home/drukos/printer_data/config/drukmix.cfg`
- active macros file: `/home/drukos/printer_data/config/drukmix_macros.cfg`
- active printer config: `/home/drukos/printer_data/config/printer.cfg`
- runtime log: `/home/drukos/printer_data/logs/drukmix.log`
- template/default config files in repo:
  - `config_examples/drukmix.cfg`
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
   - install default live config/macros only if missing;
   - patch live config paths if needed;
   - ensure `[include drukmix_macros.cfg]` exists in `printer.cfg`;
   - reload udev rules;
   - wait for `/dev/drukos-bridge`;
   - restart the service;
4. verify runtime behavior.

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
- keep `AGENTS.md` aligned if the agent-facing rules changed.

## Default stance

If there is a conflict between:
- fast temporary machine-side editing, and
- repository-driven reproducible workflow,

choose repository-driven reproducible workflow.
