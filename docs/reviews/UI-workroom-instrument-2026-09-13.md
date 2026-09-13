# Workroom instrument presentation — assistant SELF-REVIEW

2026-09-13. Base main: `07da692a6685e5f9b143bf0e02f0f8d991c5d14d`.
Product commit: `ceb840b8b7d70cd426ddcf602d420bbf3f265c52`.
This is continuation self-review with bounded agent code checks, not an
independent acceptance verdict. No matrix row or ADR-020 ruling is promoted.

Anthony's visual critique requested a living instrument while retaining the
paper, deep green ink and serif identity. The change adds a committed-event
actor trace, selected-run observation, stronger status/outcome hierarchy,
responsive evidence, sticky navigation, a compact selected-state introduction,
and system/paper/darkroom themes. The original raw ledger and all ten outcome
labels remain inspectable. Genesis report claims keep their neutral qualifier.

## Evidence, not another evaluator

`tests/browser/instrument.cjs` checks all six published fixture records with
`labels()` and `trace()`: exact stored labels, event IDs/sequences/actors, gate
outcomes, and applied-effect marks. A trace mark jumps into the unchanged raw
ledger. `longTrace()` exercises 202 events, explicit pagination, a real append
while the expanded page is focused, scroll retention, and inert hostile actor,
event type and payload text. Historical page reveals do not replay arrival
animation. The trace states that sequence position does not imply causation.

The four resource cells still use the existing explanation projection. Revision
transitions require an applied-effect source and an earlier genesis revision.
`explained_run.cjs` checks the six real records, their 259 events, exact resource
values, genesis attribution, missing citations, stored labels, and evidence jumps.
No evaluator, frozen contract, archived run, or event-hash implementation changed.
The receipt includes a `git diff --exit-code` command for those boundaries.

## Interaction checks

Selected records now refresh through GET requests, including a run started by
another browser. Presence describes time since a committed model request; it
explicitly does not assert that inference is still active. A recorded run with
no request does not acquire an inference timer. `instrument.cjs` replaces only
browser GET responses to test request age, appended responses and reduced motion.
It does not start subjects or change fixture records.

The bounded review found and corrected cross-selection polling and stale-ledger
races. `pollingRaces()` holds the prior selection's GET while a new selection
continues reading, and releases an old initial ledger page after a newer run's
snapshot has advanced. Draft tests retain review text, caret and focus across an
append. `verificationRace()` intercepts two POSTs wholly in the browser: an old
verification is hidden after append, and a delayed old-head result cannot return
into the advanced view. Those two synthetic POSTs never reach the fixture server.

Existing launch observation is retained, with request/response detail behind a
disclosure. No preview, authorization ticket, inference or provider capability
semantics change. The existing five-flag browser workflow checks reviews, local
lifecycle, bundle replay, comparisons and study planning/execution in temporary
scripted state.

## Visual checks and limits

`layout()` checks 1440, 900, 768 and 390 pixel widths: equal readable evidence
cells, no empty cells, report width at least 220px, and no document overflow.
`contrast()` samples actual computed text and composited backgrounds in both
themes, including the missing-explanation fallback. The fallback originally kept
a hardcoded light outcome background; the general outcome override corrects it.
Theme tests check system following, explicit override, reload retention and
storage containing only the theme preference. Reduced-motion assertions disable
new arrival/presence animation.

The local screenshot pass inspected the light overview, dark trace, dark evidence,
mobile overview and simulated running request. The sticky trace is independently
scrollable; its total and explicit page button disclose the retained events.
Decorative grain and rules are CSS only. These checks are presentation fidelity,
not new subject observations or evidence of model behavior.

The authoritative measured commands and final-tip resolver are in
`docs/receipts/S7-workroom-instrument.json`. Runtime tests use temporary state;
the operator process/store are only inspected for the authorized idle relaunch.
A server-memory API key, if re-entered before that relaunch, expires with the old
process and is never copied by this change.
