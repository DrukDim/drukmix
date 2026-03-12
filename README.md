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

`Klipper macro -> Moonraker remote method -> DrukMix agent -> backend -> bridge USB protocol -> ESP-NOW bridge -> pump node -> hardware driver`

The current deployed field path is `pumpvfd`, but the project is intended to remain multi-backend.

## Current scope

The project is intended to support more than one physical pump backend.

Current backend families:
- `pumpvfd` — VFD-driven pump
- `pumptpl` — analog / potentiometer / relay style pump control

The current live/deployed path is `pumpvfd`, but upper layers should not become permanently backend-locked.

## Operating assumptions

DrukMix currently assumes a deployment environment built around:
- Klipper
- Moonraker
- Mainsail
- a separate `drukmix` agent service
- the current canonical deployment layout used in this repository

Current canonical deployment layout:
- source repo: `/home/drukos/drukmix`
- runtime app dir: `/opt/drukmix`
- runtime config dir: `/etc/drukmix`
- active config file: `/etc/drukmix/drukmix.cfg`
- active macros file: `/home/drukos/printer_data/config/drukmix_macros.cfg`
- systemd unit: `/etc/systemd/system/drukmix.service`
- runtime log: `/var/log/drukmix/drukmix.log`

This means the project is currently documented and tested around the existing `drukos`-style deployment assumptions.
User/path portability is not yet a finished goal and should be treated as an active limitation, not as a solved feature.

## Workflow

Canonical workflow:

`repo -> deploy -> restart -> verify`

Rules:
- make changes in repo first;
- deploy from repo state;
- do not treat printer-side edits as canonical;
- if runtime truth changes, commit it back into repo.

## Status

Current verified state:
- host stack is Klipper + Moonraker + Mainsail + separate `drukmix` agent service;
- deployed backend is currently `pumpvfd`;
- command path is working;
- telemetry and status semantics are still under active cleanup and clarification.

## Project documents

- `README.md` — project overview
- `AGENTS.md` — short operational rules for AI-assisted work
- `WORKFLOW.md` — canonical change / deploy / verify procedure
- `ARCHITECTURE.md` — canonical architectural layers and semantics
- `KNOWN_ISSUES.md` — confirmed defects, active constraints, and open checklist items

## Notes

This repository is being cleaned up from a working internal project state into a more maintainable public structure.

The goal is not to make the project look generic.
The goal is to keep the real machine behavior, deployment reality, and control semantics explicit and maintainable.
