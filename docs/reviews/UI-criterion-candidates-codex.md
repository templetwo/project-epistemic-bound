# Web workroom criterion evidence candidates — seat 2/3

Scope: original BUILD_SPEC UI-01/02/03, web workroom at product5b7bc98,
accepted on main534c0cf. These are pointers for independent criterion review;
status remains partial and no reviewer/pass evidence is filled in by this change.
The terminal cockpit is a separate ADR-019 addition still under active review.

| Criterion | Concrete controls and observations |
|---|---|
| UI-01: actual create → step/run → inspect → pause/review → export | HTTP test_http_local_create_step_begin_reaches_real_observed_completion; test_global_review_queue_resolves_exact_run_and_leaves_observed_pause (allow/deny, actual held proposal, unrelated run unchanged); test_http_commitment_edits_survive_reopen_and_export. Browser flags PEB_TEST_LIFECYCLE and PEB_TEST_REVIEWS execute the mock local lifecycle and real scripted held-review flow, inspect actual repair/no-repair and exported review resolution events. |
| UI-02: unauthenticated/cross-origin mutations fail; hostile browser text inert | HTTP test_authentication_host_origin_and_session_rotation, read authentication cases, expiry/format/CSRF controls and hosted exact-preview checks; the bundle HTTP control also checks CSRF/cross-origin rejection. Browser opens hostile recorded model content and asserts no script/image DOM injection or page errors. |
| UI-03: pending not success; pagination explicit and complete | HTTP test_event_pagination_has_explicit_totals_and_no_missing_rows consumes123 records across pages and requires the complete ordered sequence. Typed service failure is not an HTTP success. Browser requires acknowledgement to stay waiting_review, allow/deny to become paused, and actual observed resource effects to agree with the decision. Current status/label rendering and event count/load-more presentation remain available for reviewer inspection. |

Exact receipts: docs/receipts/S5-global-review-ui-codex.json (product88579f2),
S5-comparison-ui-codex.json (product3b60280), S5-bundle-replay-ui-codex.json
(product5b7bc98). The last exact archive measured616/0/0 and all four browser
flags; the count alone is not semantic acceptance. Tests use temporary state,
scripted subjects and MockTransport, with no actual paid/model inference.

Study execution remains unbuilt. It is part of broader product/API scope;
it should not silently replace the literal text of any individual UI criterion.
Any remaining acceptance gap should be named against that criterion by its reviewer.
