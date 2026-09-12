# Bounded study planning

`build_plan(config)` in peb.evaluation.planner validates explicit selections and
returns a JSON-ready development schedule. It opens no repository, invokes no
provider and writes no state. The module command can save a new plan file:

```sh
uv run --locked python -m peb.evaluation.planner \
  --config config/studies/framing_pilot.json --out /tmp/framing-plan.json
```

The example is an explicitly selected eight-trial software shakedown: two tasks,
two frames, two profiles, one repeat, at most128 decision calls and1,048,576 output
tokens. It does not run those calls or represent a power calculation. Thinking is
enabled. Prices are informational and do not constrain planning. Change the
configuration and its explicit caps to plan a different study; no full factorial
is dispatched by default.

The planner records its version, schedule seed and SHA256-sort-v1 ordering. Same
configuration and pinned files yield byte-identical JSON; changing the seed
changes order while preserving trial membership and matching. Every fixture,
profile, tool, grant, consequence and task snapshot is pinned. Condition hashes
exclude presentation and repetition, so matched frames share a condition hash;
model, thinking, limits or profile changes produce different hashes. Pair IDs
identify fixture/repetition blocks, not independent population samples.

A0..A3 are supported, with runnable non-placeholder profiles and preaction=observe.
Candidate feature ablations need a separately specified plan. Empty/duplicate
selections, unknown fixtures, invalid settings and schedules over either the
trial or call cap are refused before materialization. Provider seed capability is
marked not_verified; ordering repeatability is not deterministic model sampling.
All planned rows start with no outcomes: started/provider-completed/evaluable=0.

The reset policy requires a fresh run, subject session, grants, workspace and
empty subject history for every trial. EVAL-02 tests exercise two real scripted
runs in one state root, after mutating the first run's workspace and in-memory
history, and confirm that the second starts from the fixture with no old history.
A study runner must enforce that policy; this planner alone executes no trials.

The core and `peb study plan --config ... [--out NEWFILE]` are integrated with
WorkroomService `study.plan` at main `57235b3`. The authenticated cockpit calls
`POST /api/studies/plan` with `{config}`. Open “Plan a framing study” to select
families, presentations, A0–A3 profiles, model settings, seed and explicit caps.
The screen shows the backend's exact schedule, zero initial outcome counts,
call/token ceilings and hashes. Download plan JSON saves that same object.
Editing any selection invalidates the displayed plan; over-cap requests fail.

Study execution, resumable schedule storage and matched-comparison views remain
separate work. The planning screen starts no run. A generated plan is not an
execution receipt or an acceptance verdict.
