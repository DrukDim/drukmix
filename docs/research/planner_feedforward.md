# Planner feedforward research

This document tracks the temporary research branch for planned-motion feedforward in DrukMix.

Status: experimental research
Branch intent: evaluate whether Klipper planned extruder motion can provide useful lead time for concrete pump control without breaking truth-preserving architecture.

## Problem statement

Current DrukMix control primarily follows live extruder motion state.

That is safe for runtime gating, but it is late for a concrete pumping system with significant lag:
- the screw can begin material demand immediately after motion resumes;
- the pump/VFD path may require substantial time to accelerate;
- the pump may continue delivering after print-side motion demand drops.

This creates a mismatch between print-side demand timing and material delivery timing.

## Research goal

Evaluate a two-signal host orchestration model:

1. planned extruder motion from Klipper planner/trapq
2. live extruder motion / print state as runtime truth gate

The intended direction is:

- planned motion becomes feedforward input;
- live motion and print/pause/fault states remain gating / safety input;
- pump control does not become planner-only truth.

## Why this branch exists

This branch is not intended to declare the final canonical solution.

It exists to:
- instrument available planned-motion data;
- measure actual planner lead time in the field;
- compare planned extruder demand against live extruder velocity;
- determine whether the observed lead is useful enough to justify host-side pump feedforward.

## Current understanding from Klipper inspection

Relevant current findings:

- Klipper extruder motion is represented in its own motion queue / trapq.
- Pressure advance is applied inside the extruder motion path, not at the host layer.
- `motion_report` can access trapq-derived position / velocity.
- `live_extruder_velocity` remains useful as a real runtime-state signal, but it does not provide enough anticipation for a laggy concrete pump system.
- Planner lead time is not a fixed universal truth; it is a host/planner/runtime property and must be measured on the target system.

## Temporary architecture rule for this research

During this research, maintain the following separation:

- planned motion = anticipatory command input
- live motion = runtime truth / permission input
- print state / pause / fault = hard gates
- backend/device telemetry = delivery/device truth

Do not collapse these into one ambiguous signal.

## Temporary implementation plan

### Phase 1: instrumentation only

Add a Klipper extra that exposes experimental planned-motion signals.

Initial target signals:
- planned extruder velocity
- planner lead seconds
- planned extruder position

This phase should not directly drive the pump.
It is instrumentation and observation only.

### Phase 2: host logging comparison

Extend DrukMix host-side code to record:
- planned extruder velocity
- live extruder velocity
- planner lead seconds
- chosen pump target
- print / pause gating state

Goal:
- quantify whether planner lead is stable and useful;
- identify divergence cases between planned and live motion.

### Phase 3: minimal feedforward integration

If Phase 1 and Phase 2 show useful results, add a minimal host-side feedforward model with small, explicit tunables.

The preferred direction is:
- keep parameter count low;
- do not re-implement Klipper planner in DrukMix;
- do not turn transport/backend telemetry into fake physical truth.

## Risks to validate

### 1. Planner truth vs runtime truth divergence

Klipper planner may know intended future motion before the machine reaches it.

That can be useful for pump anticipation, but it can also diverge when:
- pause is requested;
- a fault occurs;
- motion is cancelled or drained;
- runtime timing differs from the ideal planned timeline.

### 2. Over-anticipation

If planner lead becomes large, the pump may react too early.

That may improve concrete delivery timing, but it can also:
- reduce responsiveness;
- increase oversupply risk if runtime state changes abruptly;
- require stronger gating by live state and fault state.

### 3. Mislabeling signals

Planned motion is not measured concrete flow.
It is host-planned future demand.

Live motion is not pump delivery truth.
Backend/device telemetry is not automatically measured concrete output.

These distinctions must remain explicit.

## Temporary deliverables in this branch

This branch may contain:
- temporary docs for the research plan
- a temporary Klipper extra for instrumentation
- temporary installer support for deploying that extra
- temporary DrukMix-side logging hooks

It should not be treated as final canonical product behavior until verified.

## Expected exit criteria

The branch should produce enough data to answer:

1. how many seconds of useful planner lead are actually available on the target machine?
2. how stable is that lead during real printing?
3. how often do planned motion and live motion diverge in meaningful ways?
4. is the available lead large enough to justify pump feedforward?
5. what is the minimum tunable set needed if feedforward is adopted?

## Current research method

Current experimental probe strategy:

- do not use `motion_report` as the primary source for future extruder plan;
- mirror extruder moves when Klipper calls `PrinterExtruder.process_move()`;
- compute planned future extruder velocity from the mirrored queue;
- keep `queue_tail_s` as a separate indicator of planner horizon depth.

Why:

Earlier experiments showed that `queue_tail_s` can be large while `motion_report`-based future reads still returned no usable future velocity samples.
That means planner depth exists, but the previous read path was not the right source for forward-looking samples.

This research path remains instrumentation-only.
It does not change print behavior or pump behavior.

