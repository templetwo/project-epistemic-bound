# Recorded export projections — seat 2/3

ACCEPT `11551d3204afe6f3bb8733b80079f8c0354fc593`, parent main `9c2afc2`.
Read exact snapshot/export/test changes. In an isolated git archive,
`uv run --locked pytest -q tests/unit/test_replay_export.py
tests/acceptance/test_scenario_families.py tests/integration/test_review_route.py
--junitxml=/private/tmp/astra-export-review-11551d3.xml` passes61, skips0, fails0.
Changed-file Ruff clean. JUnit SHA256:
61443962308947ce6c8969f93cfe64341b3f576c15ae6f9c988b2fdbe5e6563e.

reviews.json uses the existing event projection and preserves recorded status;
read-time deadline expiry cannot silently replace a pending recorded review.
evaluation.json copies the last recorded evaluator payload with event identity
and timestamp, or explicitly reports absent. Earlier evaluator events remain
in events.jsonl. The projection does not recompute or license a new verdict.

Independent real-path probe: executed the correction-handoff control, recorded
two actual DefaultEvaluator results, exported, and checked that evaluation.json
exactly matches the latest record with accurate_handoff=yes; its event_id differs
from the first, which remains in exported events. A separate real held review
was denied through resolve_review_from_records; exported reviews exactly matched
the returned recorded review. No provider inference or operator state involved.
