# ADR-030 — Governed simulator live operations

2026-09-19. Implementation owner: Codex, under Anthony's explicit instruction to
implement TOT-PEB-RT-001 revision 1.0. Self-review by the same builder; independent
review remains `needs_review`. No historical lane, main checkout, or live Stack
is reopened or changed. Work is isolated on `build/live-operations` and simulator
`build/peb-live-operations`; no merge or publication is authorized by this ADR.

PEB baseline: `885de3dcb7964d1931c1e4fa5f3298b55470d41d`.
Simulator baseline: `3aad7695b8720b291999ef0903fcab7b7e008f1e` (later than the
packet pin). The intervening theme, cause/effect recorder, coach-default and
boundary-DOF/preflight changes are retained. Source-inspection tests now read the
shared PlantCore for moved methods; native trajectory/protection tests remain
unchanged in their behavioral assertions. The new inventory documents checkpoint
state, bounded RT trend retention and exercise-mode restoration.

The additive `continuous_operation_v1` profile registers a real-time reference
monitor and plant executor. It uses PEB provider adapters, protected credential
resolution and authenticated HTTP/CSRF boundary. Its SQLite store is isolated
from v1. Frozen contracts, canonical hashes, finite runs, and event hash rules
are unchanged. Node computes candidates; only SQLite commit establishes the world.
Raw model responses precede parsing, authority is resolved from stored grants,
and exact reviews never override native control protections.

Artifact manifests hash every served/runtime dependency and pin the Node runtime.
No production path evaluates HTML or imports the logic harness. The simulator's
shared PlantCore is statically extracted code used by both browser and kernel.
UI backtrack rings are view-only; real-time recovery is from a full checkpoint.
Message ID counters are checkpoint-owned rather than global module state.

Commissioning and actual-model results must be recorded separately from deterministic
tests. The packet acceptance rows are requirements, never promoted by suite count.

## Publication authorization — 2026-09-19

Anthony subsequently instructed "push and merge" for this implementation. This
supersedes the initial no-publication scope above and authorizes both implementation
branches to reach their existing repositories' main branches. Historical closed
lanes remain untouched. Tests and self-review accompany publication; paid live
qualification and independent acceptance remain pending. No additional inference
is included in this publication action.
