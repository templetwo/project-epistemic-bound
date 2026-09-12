# Seat 2/3 review — f5e0ac9

Verdict: ACCEPT f5e0ac92acd76be144a2e851d3fd224f927cbf99.

The closed comparison.get payload supplies two PebIds and a frame/profile axis.
The handler opens one repository, projects each run with its bound verifier,
keeps the repository alive for verification, and returns the core result under
comparison with recorded:false and explicit absent-anchor provenance. Unknown
runs and an absent core are refused. No evaluator is invoked and no events are
written. New composition pins the consequence model with the planner formula;
legacy evidence is not backfilled. No bind_grants change.

Validation: exact f5e0ac9 archive, 68 service tests passed, zero failed/skipped.
JUnit: /private/tmp/astra-seam-f5e0ac9.xml.
An isolated f5e0ac9 archive plus comparison core 621ee3d and legacy fixture fix
224d759 passed the full 584-test suite, zero failed/skipped; Ruff src/tests clean.
JUnit: /private/tmp/astra-seam-core-composed.xml. This composed tree is explicitly
not an exact single commit. The legacy control removes the pin before the real
manifest and genesis are recorded, retaining a valid chain and absent pin.
All tests use disposable state and scripted/mock providers.

The UI binding remains a separate review unit. This receipt accepts the service
seam and additive new-run pin, not study execution, UI-01 closure or release.
