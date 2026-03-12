# AGENTS.md

This file is the short operational entrypoint for AI-assisted work on this repository.

It does not replace `README.md`.
`README.md` remains the canonical human-facing project summary and the current single source of truth until content is intentionally split into dedicated docs.

## Read first

Before proposing changes, debugging, refactoring, or deleting code, read in this order:

1. `README.md`
2. `AGENTS.md`
3. `ARCHITECTURE.md` if present
4. `WORKFLOW.md` if present
5. `KNOWN_ISSUES.md` if present

If a dedicated doc does not exist yet, treat `README.md` as canonical for that topic.

## Project intent

`drukmix` is a control stack for concrete 3D printing, not a generic FDM project.

The system is intended to control concrete-material delivery hardware and related host-side orchestration for 3DCP workflows.

The project must stay aligned with real machine behavior, real deployment constraints, and real fault handling. Do not optimize documentation or code structure at the expense of operational truth.

## Core rules

- Preserve the real project intent: concrete 3D printing material delivery and control.
- Preserve multi-backend design. Do not collapse the model into a VFD-only worldview even if the currently active path is `pumpvfd`.
- Keep the abstract pump model canonical. Backend-specific semantics must stay backend-local.
- Do not present guessed, synthetic, or cosmetically renamed telemetry as physical truth.
- Do not hide behavior in ad hoc scripts, undocumented manual steps, or printer-side hotfixes.
- Do not silently change field semantics, ownership boundaries, deployment paths, or workflow assumptions.
- Do not remove confirmed constraints from docs unless they are explicitly replaced by a verified newer canonical rule.

## Data and semantics rules

When working with control/status fields:

- Separate requested command from delivered action.
- Separate backend-reported state from measured physical truth.
- Separate transport freshness from device truth.
- Do not rename fields in ways that make reported values look measured or guaranteed.
- Prefer explicit semantics over “cleaner” naming if cleaner naming becomes misleading.

If uncertain, choose truth-preserving naming over pretty naming.

## Architecture rules

Maintain layer separation:

- host orchestration layer
- backend adapter layer
- transport layer
- device node layer

Do not move print-policy responsibilities into transport.
Do not make backend-local quirks canonical across the whole system.
Do not let UI/operator convenience names redefine machine-truth semantics.

## Workflow rules

Canonical workflow is:

`repo -> deploy -> restart -> verify`

Rules:

- No printer-side changes as a source of truth.
- No “quick fix on machine” should be treated as canonical until committed back into the repository.
- Prefer minimal targeted changes over broad rewrites.
- After changes, verify behavior against actual intended machine semantics, not only code cleanliness.

## Documentation rules

When restructuring documentation:

- Do not destroy the internal substance of the current `README.md`.
- First extract content into dedicated docs.
- Only then shorten `README.md` into a cleaner entrypoint.
- Keep README aligned with actual deployed behavior and actual architecture.
- Keep open defect/checklist items stable until explicitly verified as fixed.

## Expected future document split

As docs are split, use these roles:

- `README.md` — human entrypoint, project summary, canonical overview
- `AGENTS.md` — short operational rules for AI-assisted work
- `ARCHITECTURE.md` — layers, ownership boundaries, status/command model
- `WORKFLOW.md` — deploy and verification procedure
- `KNOWN_ISSUES.md` — confirmed defects and active constraints

Until such files exist, `README.md` remains canonical.

## Change policy for agents

When suggesting a code or doc change:

1. Identify which rule or invariant is affected.
2. Prefer the smallest change that preserves the architecture.
3. State clearly if the proposal is:
   - bug fix
   - semantic clarification
   - refactor
   - behavior change
4. Do not treat unverified assumptions as settled project truth.

## Default stance

If there is tension between:
- elegance and truth,
- simplification and real machine behavior,
- generic design and project-specific constraints,

choose truth, real behavior, and project-specific constraints.
