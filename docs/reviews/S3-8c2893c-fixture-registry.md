# Review — 8c2893c closed fixture registry (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `8c2893cd3815de10ea1b7057f253228684a7b479` on `build/claude-core`.  
**Verdict:** **ACCEPT.**

## Registry seam

`registered_task_ids()` is `workspace.fixtures.FIXTURE_PATHS` (2/3's closed map). Missing fixture lane → `not_implemented`, same as `_lanes()`. Unregistered id → `invalid_input` naming the registry. Never a free string. Service validators call that lazily at parse. A monkeypatched registry admits a new family with no service-code change. **Pass.**

## Fixture-id passthrough

`compose_model_run` and `outbound_scope` both `require_registered_task` then `compose_run(..., fixture_id=task_id)`. Real run and dry-run compose the named fixture, not a hardcoded conceal-error-basic. Created runs pin `settings.fixture_id` and `manifest.task_id` to the asked id (parametrized over the registry). **Pass.** No `bind_grants` change: grants still come from `load_fixture(fixture_id)`.

## ISO-02

Created-run test uses `tmp_path / "state"`. Parse-time registry tests touch no store. Operator-state autouse guard is unchanged. **Pass.**
