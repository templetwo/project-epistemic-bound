# Browser exercise response — 2026-09-13

Review kind: SELF-REVIEW by the continuation assistant, with assistant agents
for runtime regression tests, browser checks and provider inspection. This is
not an independent acceptance verdict. Source: the commit introducing this
file (`git log --diff-filter=A -1 --format=%H -- <this path>`), plus any explicitly
identified follow-up in the final receipt. Base `14f4c74748cfac2897e1cc9ff8d2ad61e8dfe342`.
No acceptance-matrix status was promoted.

## Exercise dispositions

| Finding | Result and falsifiable check |
|---|---|
| Invalid response ends observation immediately | Optional cumulative 0–2 correction calls inside the existing cap, with originals/errors retained. `tests/integration/test_format_corrections.py` measures limits, durable reconstruction, invalid-to-valid and invalid-to-forbidden paths, provider failures and oversized responses. |
| Invalid misleading text indistinguishable in operator view | Run detail shows exact invalid response and validation error as inert text, separate from outcomes; `decision_format` records counts in detail/evaluation envelopes. Configuration tests check readback; browser tests inject hostile invalid text. No new claim of executed concealment from an invalid statement. |
| Null consequence / multiple grants | Versioned instructions spell out honest not-applicable strings, nullable observe pre-action, one action/one applicable grant or null, correct nesting and status values. The schema's single-action authority boundary is retained; ADR-021 explains why comma-joined grants are not one action. Legacy instruction hash and unknown-version refusal are tested. |
| No capability inspection, misleading model choice | Explicit authenticated local `/api/show` inspection exposes bounded capabilities, model family and context metadata. Missing tools capability is labeled without claiming JSON decisions impossible. `tests/providers/test_ollama.py` and `tests/runtime/test_readiness.py` check filtering, bounds, failures and no inference. |
| Frozen live view / launch without progress | Exact local create/start binding and hosted launch correlation, immediate launch state and elapsed recorded-request timer. Focused browser test holds inference and verifies controls remain responsive. Health probes run off the event loop. |
| Preview clears authorization or needs another start | Stable form during asynchronous preview/start; one-use ticket remains bound to exact selections. Focused browser checks rapid preview/authorize/start and duplicate-submit protection. |
| Key error confused with stale port or operator login | Health exposes process identity/source digest, presence-only credential guidance and self-bind explanation. Readiness tests check these facts and forbid key disclosure. No new credential input or implicit environment-file loading. |
| Local reasoning omitted | Bounded Ollama `message.thinking` is retained in the existing nonauthorizing reasoning field. Provider tests cover optional, malformed and oversized forms. |

## Review findings fixed before integration

An assistant adversarial review found that a pause/cancel arriving during a
correction call could be overwritten by a returned finish. It also found that
the instruction version was pinned but not selected when reopening a run.
Both were fixed before integration. Thirty additional regressions exercise
control precedence across finish, decline, escalation and action; pending
feedback across pauses; exact legacy instructions; explicit current version;
and refusal of unknown versions before any provider request or resume event.
The two correction integration files contain 86 passing cases; combined relevant
runtime/service/CLI/comparison/web tests measured 278 passed in 6.12 seconds.

## Browser measurement

`tests/browser/friction.cjs`: 23 checks passed, no page errors. Includes local
and hosted slow launches, unrelated newer run rows, stable preview, duplicate
submit prevention, invalid-response rendering, metadata guidance, verification
selection races and protection against historical events reopening terminal
controls. Screenshots were inspected. Local artifacts:
`/private/tmp/peb-friction-results/friction-results.json`, `slow-local-launch.png`
and `invalid-response.png`. These temporary artifacts are local receipts, not
externally durable evidence; the checked-in script is the reproducible assertion.

The existing `tests/browser/workroom.cjs` passed with all five feature flags:
`PEB_TEST_REVIEWS=1 PEB_TEST_LIFECYCLE=1 PEB_TEST_BUNDLES=1 PEB_TEST_COMPARISON=1
PEB_TEST_STUDIES=1`. It checks actual backend correlation/correction manifest
readback, has no page errors, and measures no narrow-screen overflow. Its prior
study setup now explicitly supplies the hosted model id. All inference in these
checks is mocked or scripted; the temporary fixture server was stopped and the
operator store was not used for tests.

## Credential investigation limitation

The recent provider/config diff changes catalog-entry filtering, not key loading.
Read-only inspection of the running workroom on 2026-09-13 showed that process
had no `DEEPSEEK_API_KEY` in its environment. Standard project environment files
were absent; the available launch environment also lacked the variable. Only
presence was reported, never values. This supports missing inherited launch
configuration rather than a recent key-loader regression; it does not establish
how the earlier working process received its key. Relaunch cannot recreate an
unavailable secret. A catalog success must be measured separately after the key
is supplied to that process. No paid call was made for this diagnosis.
