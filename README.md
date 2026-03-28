# DrukMix

DrukMix is a control stack for concrete 3D printing material delivery.

It is designed for 3DCP systems built around:
- Klipper
- Moonraker
- Mainsail
- an external pump / mixer control path
- custom host-side and firmware-side control logic

This is **not** a generic plastic FDM project.

## What it does

DrukMix connects print-side motion and operator commands to a concrete material delivery system.

Current host control chain:

`Klipper macro -> Moonraker remote method -> DrukMix driver -> backend -> bridge USB transport -> bridge node / link -> pump node -> hardware driver`

The current deployed field path is `pumpvfd`, but the project is intended to remain multi-backend.

## Current scope

The project is intended to support more than one physical pump backend.

Current backend families:
- `pumpvfd` — VFD-driven pump
- `pumptpl` — analog / potentiometer / relay style pump control

The current live/deployed path is `pumpvfd`, but upper layers should not become permanently backend-locked.

## Current deployment model

DrukMix is currently deployed from a normal repository checkout and runs directly from that checkout.

Current canonical deployment layout:
- source repo: `/home/drukos/drukmix`
- systemd unit: `/etc/systemd/system/drukmix.service`
- active driver config file: `/home/drukos/printer_data/config/drukmix_driver.cfg`
- active controller config file: `/home/drukos/printer_data/config/drukmix_controller.cfg`
- active macros file: `/home/drukos/printer_data/config/drukmix_macros.cfg`
- active printer config: `/home/drukos/printer_data/config/printer.cfg`
- runtime log: `/home/drukos/printer_data/logs/drukmix_driver.log`
- default example config templates in repo:
  - `config_examples/drukmix_driver.cfg`
  - `config_examples/drukmix_controller.cfg`
  - `config_examples/drukmix_macros.cfg`

The live config and macro files are intentionally placed in the printer config directory so they can be viewed and edited through the normal Klipper / Mainsail config UI.

The `config_examples/` files are installer defaults and repository templates.
They are not the live machine-side source of truth after install.

## Operating assumptions

DrukMix currently assumes a deployment environment built around:
- Linux
- systemd
- Klipper
- Moonraker
- Mainsail
- a separate `drukmix` driver service
- a printer config directory under the active user home
- udev-based stable serial aliasing for the bridge device

Current normal install flow expects a host environment where the helper can:
- create a Python virtual environment;
- install Python dependencies;
- install a global `drukmix` command launcher;
- install / reload a systemd unit;
- install or keep live config files under `~/printer_data/config`;
- install bridge udev rule, reload udev rules, and wait for the bridge alias to appear.

After a successful install or update, the helper installs a global launcher at `/usr/local/bin/drukmix`
that forwards to the repository checkout's `tools/drukmix` script.

## Host prerequisites

Current practical host-side requirements include:
- `python3`
- `python3-venv`
- `pip` via the venv bootstrap flow
- `systemd`
- `curl`
- `udevadm`
- `getent` or an equivalent way to resolve the current user home directory

Python package dependencies are listed in `requirements.txt`.

Non-Python host tools are operating-system requirements and are not tracked in `requirements.txt`.

## USB bridge identity

The current installation flow expects the bridge serial device to become available as:

`/dev/drukos-bridge`

This is currently achieved through Linux `udev` rules and a stable USB-identity match.

At the moment, the bridge is still seen by the OS using a generic CP2102-style USB identity such as:

`usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`

That is operationally sufficient for the current Linux + udev installation model, but it is not yet the desired long-term device identity strategy.

The project should move toward clearer and more intentional device identity for bridge and pump nodes, especially for first-install and multi-machine deployment scenarios.

## Planner-authoritative pump control

DrukMix is transitioning from mixed Moonraker-derived motion/lifecycle gating toward planner-authoritative automatic pump control.

Canonical direction:

- `drukmix_planner_probe` is the printer-side motion authority for automatic pump orchestration;
- planner-derived extruder velocity is treated as scheduled future demand;
- `motion_report.live_extruder_velocity` is not intended to remain a separate control authority;
- printer lifecycle fields such as `print_stats.state`, `pause_resume`, and `idle_timeout` are not intended to remain automatic pump-control gates;
- backend fault/manual/offline handling remains independent.

Current production planner contract is intentionally compact:
- `queue_tail_s`
- `print_window_active`
- `time_to_print_start_s`
- `time_to_print_stop_s`
- `control_velocity_mms`

Current config ownership model:
- driver runtime values are owned by `[drukmix_driver]` in `drukmix_driver.cfg`;
- controller lookahead/policy values (`pump_start_lookahead_s`, `pump_run_lookahead_s`, `pump_stop_lookahead_s`, prestart/prestop behavior, velocity mapping) are owned by `[drukmix_controller]` in `drukmix_controller.cfg`;
- Klipper planner-probe section is managed directly inside `printer.cfg` by the install/update helper;
- do not create a separate `drukmix_planner.cfg` unless there is an explicit verified request to reintroduce that file.

Research-style multi-horizon planner fields such as `planned_v_now` ... `planned_v_15000ms` are not intended to remain in the production control path.

Current deployment-stage expectation:
- automatic operation is expected to run in backend mode `AUTO`;
- backend mode `MANUAL` blocks automatic orchestration;
- backend mode `UNKNOWN` also blocks automatic orchestration;
- physical MANUAL/AUTO switching is planned future integration, not something to be approximated by weakening `UNKNOWN` handling.

This direction has been validated sufficiently to justify architectural migration, but the final agent cleanup and the exact cold-start / run / stop lookahead policy are still being formalized.

Relevant files:
- `klipper_extra/drukmix_planner_probe.py`
- `docs/research/planner_feedforward.md`

## Workflow

Canonical workflow:

`repo -> deploy -> restart -> verify`

Rules:
- make changes in repo first;
- deploy from repo state;
- do not treat printer-side edits as canonical;
- if runtime truth changes, commit it back into repo.

Quickstart (Moonraker/Mainsail):
1. Add an Update Manager entry for this repo (example):
   ```
   [update_manager drukmix]
   type: git_repo
   path: /home/drukos/drukmix
   origin: <your-remote-url>
   primary_branch: feature/hybrid-klipper-controller
   post_update: /home/drukos/drukmix/tools/drukmix install
   ```
   Adjust paths/user/branch as needed.
2. After Update in Mainsail/Moonraker:
   - Klipper: `systemctl restart klipper` (reloads the controller extra)
   - Driver: start/restart your service or run `DRUKMIX_CONFIG=~/printer_data/config/drukmix_driver.cfg python3 /home/drukos/drukmix/drukmix_driver.py`
3. If you want auto-start for the driver, run `tools/drukmix install` once with the required privileges. The service is optional and can be skipped on systems without systemd.

This keeps updates reproducible: pull via Update Manager, run the setup helper, restart services, verify.

## Status

Current verified state:
- host stack is Klipper + Moonraker + Mainsail + a separate `drukmix` driver service;
- deployed backend is currently `pumpvfd`;
- the command path is working;
- example-based live config install is working;
- install now waits for `/dev/drukos-bridge` before service restart;
- telemetry and status semantics are still under active cleanup and clarification.

## Current limitations

Current known limitations include:
- deployment is still oriented around the current Linux + systemd + Klipper/Moonraker/Mainsail environment;
- live deployment portability to other host layouts is not yet a finished goal;
- the currently deployed live path is `pumpvfd`, even though the architecture is intended to remain multi-backend;
- telemetry semantics are still being cleaned up to better separate requested, delivered, backend-reported, and real physical state;
- bridge USB identity is still generic at the base USB-device level and currently depends on udev aliasing for stable attachment;
- flashing and first-install provisioning of blank bridge/pump ESP-based devices is not yet a canonicalized installer workflow;
- planned-motion feedforward is still experimental research and not yet a canonicalized host-control path.

## Project documents

- `README.md` — project overview
- `AGENTS.md` — short operational rules for AI-assisted work
- `WORKFLOW.md` — canonical change / deploy / verify procedure
- `ARCHITECTURE.md` — canonical architectural layers and semantics
- `KNOWN_ISSUES.md` — confirmed defects, active constraints, and open checklist items
- `docs/research/planner_feedforward.md` — temporary research plan for planner-aware feedforward

## Notes

This repository is being cleaned up from a working internal project state into a more maintainable public structure.

The goal is not to make the project look generic.
The goal is to keep the real machine behavior, deployment reality, and control semantics explicit and maintainable.
