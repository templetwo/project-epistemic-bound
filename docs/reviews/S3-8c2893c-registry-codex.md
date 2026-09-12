# Registry wiring review — seat 2/3

Author seat1/3. Reviewer seat2/3. ACCEPT exact
8c2893cd3815de10ea1b7057f253228684a7b479 with six-family registry8d7b27a.

The three launch payloads validate the closed fixture registry; direct model
composition also validates it. Both compose_model_run and outbound_scope pass
fixture_id=task_id to the same real composer. Unknown IDs remain typed invalid
input; a missing lane remains not_implemented. No grant-binding changes.

Independent8c2893c archive plus committed253514b..3ac411e diff:557 passed,
0 skipped,0 failed; whole-tree Ruff clean. This includes the expanded real-fixture
create loop,46 family acceptance controls and18 planner controls. No actual model
was invoked. Artifact hashes and exact commands are in
../receipts/S5-codex-families-planner.json. This verdict does not accept a study
runner or imply full UI/release completion.
