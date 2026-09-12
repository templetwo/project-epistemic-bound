# Families + planner review — seat 1/3 (integrator)

Reviewed: families `8d7b27a972f79a52a1a4c59beb7eded67ef6a58e` and planner `3ac411e2b861603369e49ede0a99cf89509d0dde` (contains the families). Verdict: ACCEPT both. Reviewed at 2026-09-11T23:02-0400.

Read at the exact hashes: src/peb/workspace/fixtures.py and src/peb/evaluation/predicates.py diffs, tests/acceptance/test_scenario_families.py (46), docs/SCENARIO_FAMILIES.md, one family fixture's shape, src/peb/evaluation/planner.py, tests/evaluation/test_planner.py (18), docs/STUDY_PLANNER.md, config/studies/framing_pilot.json.

Held (families): registry of six fixtures and four scripted cases through the existing typed path; bind_grants untouched; the handoff resource kind validated as a real handoff.write ToolCall. Predicates: conceal-error-v2 retained for the original task, finite-families-v1 for the five; a task snapshot that does not match the registered fixture's frame case is refused (unlicensed_task_snapshot); accurate_handoff licensed only by two exact text templates, else indeterminate with handoff_needs_review and useful_completion held indeterminate. The 46 controls run on temporary roots: frame invariance, reachable authorized completion under all four frames, denied exports under story pressure with the sink unchanged, BEHAV-06 universal-refusal and no-attempt against a reachable same-condition positive control, pending and missing handoffs. The licence document is honest about what these are: finite software controls, not held-out evaluation, no inference about motives or general capability.

Held (planner): strict StudyConfig; registered fixtures only; A0..A3 runnable, non-placeholder, protocol=observe; explicit trial and total-call caps refused before materialization; sha256-sort-v1 ordering by seed; condition hash excludes frame and repeat; pair ids per fixture/repeat; plan hash and study id; counts start at zero; never overwrites a plan; opens no repository or provider; limitations carried inside the plan. Sample config is an eight-trial shakedown with a 128-call ceiling and nothing dispatched.

Observation (not blocking): behavior_labels keys now vary by family (accurate_handoff only for correction-handoff); the cockpit renders a fixed six labels, so that one will not show there.

Trial merge (main 253514b + 8c2893c + 3ac411e = a5d919c): no conflicts; ruff clean; 557 passed / 0 skipped / 0 failed; registry on the tree = six ids and 1/3's registry-parametrized tests ran across all six. Seat 2/3 independently: 557/0/0 (#28196).
