# Global review listing — seat 2/3

ACCEPT `43835f858b80320a57d729aebaf77f895afc2f0e`, parent main `9c2afc2`.
Read the exact bootstrap/service/test diff and runtime expiry predicate.
Measured isolated git archive with `uv run --locked pytest -q
tests/integration/test_service.py tests/runtime/test_service.py
tests/integration/test_review_route.py --junitxml=/private/tmp/astra-global-review-43835f8.xml`:
74 passed, zero skips/failures. Changed-file Ruff clean. JUnit SHA256:
fe34dc4aa01e02b432bc7207ed2fcba3ab8aa9aa91d544585f16482c519e1eaf.

One global closed operation opens the repository once and reconstructs review
records from each run's events. Resolution retains its exact run/review binding.
The recorded status is preserved; effective_status applies the same deadline
comparison as the runtime without recording expiry. Existing tests cover two
held runs, per-run denial, open-first ordering and injected-clock expiry without
new events. An independent open spy observed one store open and compared the
entire before/after event sequence for exact equality.

The UI must use returned effective_status and open/total counts, and distinguish
an elapsed deadline from a recorded resolution. A queue is a read-time view;
resolution still rechecks the authoritative run and held proposal. Listing
neither grants authority nor resumes a subject.
