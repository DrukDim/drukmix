# VARIABILITY_MODEL.md

This file defines the canonical variability model for `drukmix`.

`drukmix` must remain one canonical core project.
Differences between installations must be handled as explicit, classified variation around that core, not by inventing a new repository structure, a new workflow, or a new unofficial variant for every machine.

## Purpose

The goal is:

- one canonical `drukmix` core;
- explicit and stable points of variation;
- consistent onboarding of new machines;
- minimal duplication;
- clear separation between:
  - core behavior,
  - machine-specific integration,
  - backend-specific behavior,
  - environment and compatibility constraints.

## Core rule

A new printer must not create a new `drukmix` architecture.

A new printer must use the same canonical core and add only explicit overrides in approved variation layers.

## Variability classes

### 1. Core

Core is the shared canonical behavior of `drukmix` across installations.

It includes:

- the host runtime driver;
- the planner-authoritative control model;
- the Klipper planner probe;
- the Klipper controller logic;
- the abstract pump model;
- the transport model;
- the canonical deploy workflow;
- canonical semantics and truth-label rules for status and control fields;
- canonical project documentation.

Core must not contain accidental machine-specific naming, host-specific filesystem assumptions, or backend-local semantics unless those have been explicitly promoted into canonical project rules.

### 2. Environment-specific

Environment-specific variation covers host/runtime deployment differences that do not redefine machine control semantics.

Examples:

- host class:
  - mini PC,
  - CB1 + Manta style host,
  - other Linux host layouts;
- system user;
- home directory;
- actual filesystem paths;
- service manager availability such as `systemd`;
- `udev` behavior;
- serial attachment details;
- packaging and install prerequisites.

Rule:

Environment-specific differences belong to the deployment/install layer.
They must not require forks of core control logic.

### 3. Machine-specific

Machine-specific variation covers differences that belong to the printer as a machine.

Examples:

- printer name;
- `printer.cfg` integration;
- include structure;
- kinematics;
- printer-local macro overrides;
- machine-specific pause/cancel integration;
- machine-local defaults where those defaults are truly local to that machine.

Rule:

A machine-specific layer must not duplicate core `drukmix` files.

A machine-specific layer may:

- include core components;
- provide explicit local overrides;
- define machine-local integration details;
- document what is different and why.

### 4. Backend-specific

Backend-specific variation covers differences that belong to the pump/control backend family.

Examples:

- `pumpvfd`;
- `pumptpl`;
- future VFD families beyond current supported models;
- future TPL control variants;
- backend-local `AUTO` / `MANUAL` / `FWD` / `REV` semantics;
- backend-local capability differences;
- backend-local fault handling.

Rule:

Backend-specific meaning must remain backend-local unless explicitly promoted into canonical shared architecture.

### 5. Compatibility-specific

Compatibility-specific variation covers differences caused by upstream software behavior or version changes.

Examples:

- Moonraker RPC or websocket behavior;
- Klipper object/status behavior;
- Mainsail macro defaults;
- behavior changes introduced by upstream updates.

Rule:

Compatibility issues must be tracked as explicit compatibility constraints or managed mitigations.
They must not silently redefine machine semantics, backend semantics, control authority, or truth semantics.

## Non-mixing rules

These variability classes must remain separate.

The following are not allowed:

- environment-specific paths, users, or service details becoming part of a machine profile;
- backend-specific semantics becoming part of a printer profile;
- compatibility workarounds being documented as canonical machine behavior;
- printer-local macros or config overrides being silently absorbed into core;
- creating a new repository structure for a new printer without an explicit architectural decision.

## Canonical extension rule

Every new installation should be described as:

`core + environment adaptation + machine integration + backend selection + compatibility notes`

It must not be described as:

- a separate copy of `drukmix`;
- a machine-specific fork of the architecture;
- a one-off local workflow;
- an ad hoc deployment variant that lives outside canonical documentation.

## What may vary

### Allowed environment variation

- system user;
- home path;
- service installation details;
- `udev` attachment details;
- host package/install details;
- host layout assumptions needed by installer logic.

### Allowed machine variation

- printer config include structure;
- printer-local macro overlays;
- machine naming;
- machine-local printer integration details;
- machine-local defaults, if those defaults are explicitly local.

### Allowed backend variation

- backend family selection;
- backend series/model profile;
- hardware capability profiles;
- backend-local fault handling;
- backend-local manual/auto/reverse semantics.

### Allowed compatibility variation

- documented support constraints;
- managed mitigations for upstream changes;
- installer-side normalization for known upstream defaults;
- explicit compatibility notes and validation requirements.

## What must stay core

The following must remain canonical core rules unless intentionally replaced by a newer verified project rule:

- planner-authoritative automatic pump control model;
- layer separation;
- truth-preserving status semantics;
- canonical deploy workflow;
- abstract pump model first;
- ownership boundaries between:
  - orchestration,
  - backend,
  - transport,
  - device;
- `UNKNOWN` mode blocking automatic orchestration;
- separation between:
  - requested,
  - delivered,
  - backend-reported,
  - measured truth.

## Rule for new printer bring-up

Every new printer must follow the same order:

1. Install the canonical core baseline.
2. Verify what works without local overrides.
3. Record only confirmed machine-specific differences.
4. Add a machine-specific layer only where baseline behavior is insufficient.
5. Do not change core for a problem that is local to one machine.
6. If a local issue reveals a real core defect, classify it explicitly as a core defect before changing core.

## Change classification rule

Every change must be classified as one of:

- core change;
- environment/deployment change;
- machine-specific change;
- backend-specific change;
- compatibility change.

If a change affects more than one class, that must be stated explicitly.

## Current practical direction

At the current project stage, it is still too early to freeze one final file/folder layout for all machine profiles forever.

However, it is already necessary to freeze the variability model:

- what kinds of variation exist;
- what belongs to each class;
- what must not be mixed;
- what a new printer is allowed to override;
- what must remain canonical core.
