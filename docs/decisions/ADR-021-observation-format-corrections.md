# ADR-021 — bounded format corrections and observable launches

Date: 2026-09-13. Status: implemented under Anthony's browser-exercise direction,
"address all issues push and re launch then standbye for followup". This is a
scoped continuation, with assistant implementation review, not an independent
acceptance verdict. ADR-020 item (a) remains open. The historical lane branches
and the closed board remain untouched.

## Problem and scope

The exercise repeatedly ended at a malformed decision envelope. An invalid
response can contain informative text, but it has not authorized or executed an
action. Discarding that distinction would contaminate the behavioral measures;
making every first formatting error terminal also prevents further observation.
The launch form additionally obscured progress and made preview authorization
unstable, while readiness lacked model metadata and process identity.

This decision amends BUILD_SPEC §9.1's immediate termination after parse failure
only when the operator selects format assistance. It adds to INTERFACES §§14–16.
The frozen decision schema, grant rule, event hash rule and §§1–12 are unchanged.
It also records the user's authorization to edit the web/runtime/provider paths
for these findings; it does not reassign the old lanes or resolve the independent
review requirement for acceptance-matrix promotions.

## Decision

- A run pins `format_correction_limit`, a strict integer from 0 to 2, at genesis.
  CLI/API defaults remain 0; the browser displays a choice initially set to 1.
  Study runs retain 0. The allowance is cumulative across the entire run and
  consumes the existing model-call budget, never additional calls above its cap.
- On an eligible malformed response the original `model_response` and
  `decision_invalid` remain committed. The latter records whether a correction
  was scheduled. No proposal, grant decision or effect comes from invalid output.
  The next call receives that exact response and its validation error, with an
  instruction to correct the format while preserving the intended decision.
  Its request identifies the invalid step and correction number. Oversized
  content, provider errors and exhausted budgets remain terminal; there is no
  provider-error retry or automatic schema coercion.
- Pause/cancel still apply during a call. A pending correction and its cumulative
  count survive reconstruction. Every attempt has a distinct step. A corrected
  action still passes the ordinary parser, reference monitor and executor.
- `decision_format` accompanies run detail and recorded evaluation envelopes:
  allowance, invalid-response count, actual correction-call count, affected event
  ids and whether assistance was used. It is diagnostic data, not an outcome
  flag or behavioral `claim_corrected`/`supported_correction` credit. Invalid raw
  statements remain inspectable and are explicitly unvalidated. Earlier failed
  runs are neither resumed automatically nor rescored as executed concealment.
- New runs pin the decision-instruction version. Context construction selects
  the recorded version; legacy runs retain their original instructions. An
  unsupported pin is refused instead of silently substituting a new prompt.
  Matched comparisons retain this pin and the correction allowance, preventing
  assisted and unassisted conditions from being pooled silently.

## The two reported schema ambiguities

The contract describes one tool action per decision. `claimed_grant_id` names
one applicable grant, or JSON `null` when no grant is claimed. Repair and check
are separate actions; comma joining two grants does not express one valid action.
The instructions now say this directly, including the nested action shape and
the report-status enum. A list would change the authority contract without
solving an observed need to execute two tools in one decision.

`consequence_of_not_acting` is a required string when `pre_action` is supplied.
For inspection, an honest string such as "Not applicable: this only reads the
workspace" expresses no material consequence; no consequence need be invented.
Under the observe protocol, `pre_action` may itself be null. The prompt now makes
both encodings explicit and rejects neither abstention nor this factual wording.
The strict schema is retained; format assistance makes an accidental null
correctable without pretending it was a validated action.

## Operator experience and provider readiness

- Local observation first records a run, then starts that exact id. Hosted
  observation keeps its preview-bound start and carries a random `ui_launch_id`
  through the preview, manifest and run list. Only that id can select the launch
  being watched. This transport correlation is excluded from scientific matching.
- The form stays stable while preview/start are pending. Selection changes
  invalidate the preview. Immediate launch status and elapsed time since the
  committed model request remain visible while inference is pending. The UI
  renders raw invalid content as inert text and shows validation/correction data.
- Authenticated `health.get` accepts an optional exact `ollama_model` and reads
  `/api/show` locally without inference or model download. Only bounded,
  allowlisted capability and model metadata are returned. Tool support and this
  harness's JSON decision format are different capabilities. A missing `tools`
  tag is disclosed but does not blacklist an installed model; actual decision
  compatibility remains `not_tested`. Advertised context length is distinguished
  from the active context length, which this metadata does not establish.
- Health reads run blocking local probes outside the event loop and report the
  service PID, service-construction timestamp and source digest. A port bind
  probe may see this service's own socket; `in_use` alone proves no stale process.
  Credential guidance explains that provider keys come from the server process
  environment and signing in cannot update them. No browser API-key field is
  introduced, and neither keys nor process environments are returned.
- Ollama's optional `message.thinking`, when returned, is retained in the existing
  bounded `ModelResponse.reasoning` evidence field, as DeepSeek reasoning is under
  ADR-017. It is not a second decision channel and does not authorize an action.
  This change does not request a new thinking mode.
- FastAPI's public docs/OpenAPI routes remain disabled. The authenticated
  readiness control and this interface record provide the needed inspection;
  browser access directly to Ollama is unnecessary.

## Checks and limits

Assertions are in `tests/integration/test_format_corrections.py`,
`tests/integration/test_correction_configuration.py`,
`tests/runtime/test_readiness.py`, `tests/providers/test_ollama.py`, and
`tests/browser/friction.cjs`. The existing full browser harness also exercises
real create/list/readback, reviews, lifecycle, bundles, comparisons and studies.
The dated review and receipt identify measurements and their exact source tree.
All inference in these checks is mocked or scripted. No new behavioral result,
live paid model success or independent acceptance is claimed.

Provider protocol references inspected for this change:
[Ollama show model details](https://docs.ollama.com/api/show) and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
