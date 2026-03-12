# ARCHITECTURE.md

This file defines the canonical architectural model of `drukmix`.

Until explicitly replaced by a newer canonical rule, this document describes the intended control structure, ownership boundaries, and semantics model of the project.

If any implementation, refactor, or documentation change conflicts with this file, treat that as an architectural issue and resolve it explicitly.

## Project scope

`drukmix` is a control stack for concrete 3D printing material delivery.

It is not a generic FDM stack.
It must remain aligned with real 3DCP machine behavior, real pump-control constraints, and real deployment/verification practice.

The architecture must support more than one pump backend.
The current active field path is `pumpvfd`, but the canonical model must not collapse into a VFD-only design.

## Architectural layers

Canonical layers:

1. host orchestration layer
2. backend adapter layer
3. transport layer
4. device node layer

These layers must remain conceptually separate even if some implementation details currently live in nearby files.

### 1. Host orchestration layer

Responsibility:

- translate print/job intent into host-side pump-control intent;
- manage runtime coordination with printer state and print state;
- apply high-level control policy;
- decide when commands should or should not be issued;
- handle orchestration-level fault response and pause behavior.

This layer owns orchestration logic.
It must not depend on pretending that backend-reported values are physical truth.

### 2. Backend adapter layer

Responsibility:

- map canonical abstract pump control into backend-specific command/state semantics;
- normalize backend-specific status into the canonical host-visible model;
- keep backend-local quirks contained inside the backend boundary.

This layer is where backend-specific meaning belongs.
Do not leak backend-local semantics into the global project model unless they are intentionally promoted into canonical architecture.

### 3. Transport layer

Responsibility:

- move commands and status between host and device;
- handle communication framing, sequencing, freshness, and delivery mechanics;
- report transport-level success/failure/freshness state.

Transport is not allowed to own print policy.
Transport must not silently redefine machine behavior.
Transport success does not mean physical action succeeded.

### 4. Device node layer

Responsibility:

- perform actual device-side action;
- expose device-side facts and device-reported status;
- execute firmware-level logic and hardware-facing behavior.

This is the closest layer to machine truth, but even device-reported values must still be labeled according to what they really mean.

## Canonical model rules

### Abstract pump model first

The abstract pump model is canonical.

Rules:

- host logic must target a backend-independent pump model first;
- backend-specific command shape must be derived from the abstract model;
- documentation must describe canonical behavior before backend-specific detail;
- implementation may optimize for current backend, but architecture must not become backend-locked.

### Multi-backend requirement

The system must remain capable of supporting multiple pump backends.

Current families include:

- `pumpvfd`
- `pumptpl`

Even if only one path is currently active in practice, canonical naming and architecture must avoid hard-coding backend-specific worldview into shared abstractions.

### Backend-local semantics stay local


## Device identity and attachment rules

Stable device identity is an architectural concern, not only an installer convenience.

Rules:

- host attachment must prefer explicit and stable device identity over incidental host-local enumeration;
- transport attachment must not depend on fragile `/dev/ttyUSB*` ordering;
- Linux `udev` aliasing is an acceptable current implementation mechanism, but it is not the same thing as a fully solved canonical device identity strategy;
- generic USB bridge identity must not be confused with intentional project-level device identity;
- first-install / blank-device provisioning must be treated as a distinct lifecycle stage from normal steady-state runtime attachment.

Implication:

- a device that is operationally reachable is not automatically well-identified;
- future bridge/pump flashing and provisioning work must preserve the separation between device identity, transport attachment, and runtime control semantics.

Backend-specific semantics must remain backend-local unless explicitly promoted into canonical shared meaning.

Do not let:
- VFD-specific flags,
- TPL-specific assumptions,
- transport-specific delivery details,
- convenience UI naming

become the canonical meaning of shared fields without an explicit architectural decision.

## Command ownership model

Canonical command chain:

1. operator intent
2. host orchestration command
3. backend command
4. transport command
5. device action

These are not interchangeable.

### Operator intent

This is the high-level desired machine outcome.

Examples:
- start material delivery;
- stop material delivery;
- change target output;
- recover from fault.

### Host orchestration command

This is the host-layer decision about what should be requested from the backend, given printer/print/runtime context.

It may include policy logic such as:
- do not command flow under certain states;
- debounce state transitions;
- pause or suppress command emission;
- maintain requested target through orchestration rules.

### Backend command

This is the backend-specific expression of canonical host intent.

It may translate abstract requested flow into:
- target percent,
- backend state transition,
- command packet payload,
- backend-specific flags.

### Transport command

This is the communication-level representation of backend command delivery.

It may include:
- sequence ids,
- framing,
- freshness state,
- ack state,
- link success/failure.

Transport success only means the command was transmitted/acknowledged at transport level.
It does not prove machine action truth.

### Device action

This is the actual machine-side behavior after firmware/hardware interpretation.

This is what physically matters.

## Status ownership model

Canonical status chain:

1. device fact
2. transport status
3. backend-normalized status
4. host orchestration context
5. UI/operator status

These layers must not be collapsed into one ambiguous status view.

### Device fact

The closest available representation of actual device-side state.

Examples:
- device-reported running state;
- device-reported mode;
- device-side fault state;
- device-side applied output;
- measured values, if real measurement exists.

### Transport status

Communication-layer truth.

Examples:
- link up/down;
- freshness;
- last seen timestamp;
- last acknowledged sequence;
- timeout condition.

Transport freshness is not physical truth.

### Backend-normalized status

Backend adapter output that maps backend-specific status into shared host-visible semantics.

This layer must preserve truth labels.
Do not rename values in ways that make reported values appear measured or guaranteed.

### Host orchestration context

Host-owned runtime interpretation.

Examples:
- current requested target;
- whether control is suppressed by print state;
- whether pause was triggered by orchestration policy;
- whether command emission is intentionally inhibited.

This is not device truth.
It is orchestration truth.

### UI/operator status

Presentation-layer summary for operator understanding.

Useful, but dangerous if it overwrites deeper truth semantics.
UI convenience must not redefine canonical field meaning.

## Field truth rules

Every important control/status field should be treated according to what kind of truth it represents.

Canonical truth classes include:

- `requested`
- `delivered`
- `acknowledged`
- `backend_reported`
- `measured`
- `stale`

Rules:

- do not rename `backend_reported` values to look like `measured`;
- do not rename `acknowledged` values to look like delivered physical action;
- do not treat stale values as current truth;
- do not let cleaner naming hide weaker truth semantics.

If a field is not truly measured, do not imply that it is measured.
If a field is only backend-reported, say so.
If a field is only transport-fresh, say so.

## Telemetry rules

Telemetry must represent reality as honestly as possible.

Rules:

- no synthetic telemetry should be presented as physical truth;
- no guessed values should be labeled as measured;
- no cosmetic rename should increase semantic certainty;
- reporting path must preserve distinction between command target, backend-reported result, and physical fact.

Truth-preserving naming is preferred over aesthetically simpler naming.

## Fault-handling rules

Fault handling must remain explicit about ownership.

Possible owners include:
- device-side fault behavior,
- transport failure handling,
- backend-level interpretation,
- host orchestration response.

Do not collapse all fault behavior into a single ambiguous “fault” concept if the recovery semantics differ by layer.

Host pause behavior, backend fault state, and transport disconnect are related but not equivalent.

## Refactor constraints

Refactors must preserve:

- layer separation;
- truth-preserving field semantics;
- multi-backend architectural viability;
- explicit command/status ownership;
- repository-documented deployment reality.

Refactors must not optimize for code neatness by erasing meaning.

## Documentation alignment rules

When architecture changes:

- update `README.md` if canonical overview changed;
- update `ARCHITECTURE.md` for structural or semantic changes;
- update `AGENTS.md` if operational guidance changed;
- update `WORKFLOW.md` if deployment/verification procedure changed;
- update `KNOWN_ISSUES.md` if an issue was introduced, clarified, or verified as fixed.

## Default stance

If there is tension between:
- elegant abstraction and truthful semantics,
- backend convenience and multi-backend architecture,
- transport simplicity and correct ownership boundaries,

choose truthful semantics, correct ownership boundaries, and multi-backend architectural integrity.
