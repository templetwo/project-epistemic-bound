# Cockpit bindings review — seat 1/3 (integrator, runtime owner)

Reviewed: `744033077481afd25f9625e4938f0c6a94337f0f` (parent b9572c9; its tests need the reviewed trio, verified at the merged tree). Verdict: ACCEPT. Reviewed at 2026-09-11T22:43-0400.

Read at the exact hash: src/peb/web/app.py diff, tests/web/test_workroom.py (28), static/app.js diff, docs/WORKROOM.md, receipts.

Held:
- Routes: `POST /api/runs` → run.create (create only, §15); `POST /api/runs/observe` → run.start (bounded hosted launch, preview-token gated); `/{id}/step`, `/{id}/start` → run.begin; `/{id}/commitments/{cid}/accept|revise`.
- Hosted lifecycle is REFUSED at the web layer (409 for a deepseek run.create, and for step/begin on a deepseek run) and pointed at the bounded launch — the conservative option ADR-018 allowed. Tested for all three routes; the service is never called.
- Preview: a token is issued whether or not rates were supplied (`cost_available` says which); scope display and exact single-use binding remain mandatory — Anthony's rule that missing rates hold nothing (ADR-017 addendum 2). Thinking chosen explicitly is bound into the token; a start that changes it is refused (tested).
- Two real end-to-end HTTP tests on the real WorkroomService: local create → step → begin reaches a completed, evaluated run; operator commitment accept/revise survives reopen and the export matches run.get.
- `peb serve` boots the merged tree (index 200, unsigned health 401, wrong Host 403).
- Trial merge onto main d0f878d: no conflicts; ruff clean; 491 passed / 0 skipped / 0 failed (28 web tests).

Not claimed: full UI-01 (docs/WORKROOM.md keeps its outstanding-scope section: study operations, global review views, hosted lifecycle in the web).
