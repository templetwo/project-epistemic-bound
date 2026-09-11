# Lane — seat 2/3

Branch: `build/codex-workroom`. Current revision is the commit carrying this file
(`git log -1 --format=%H -- docs/lanes/codex.md`). Base main20a0c5b; provider tests
7851d70 (29 cases) accepted against provider953921e, board #27985.

Cockpit slice accepted by seat1/3 #28010 and merged main9a74b3e. Real
WorkroomService transport, loopback authentication/CSRF, bounded hosted preview
and start, scripted controls, run inspection, review, evidence and export UI.
The serve stub assertion was removed with seat1/3 authorization #27678.

Validation: 22 API cases passed on isolated953921e plus this cockpit; own base
21 passed/1 explicit preview dependency skip. Browser QA: hostile text inert,
actual scripted outcome visible, 390px mobile has no horizontal overflow, no
script errors. Whole release is not claimed. Provider exact re-review receipt:
docs/reviews/PROVIDER-953921e-codex.md. Prior reviews remain under docs/reviews/.

Remaining: full UI-01 step/start/commitments/study operations; release checker and
51-row matrix; five scenario families; bounded planner/EVAL-02 and BEHAV-06.
No paid smoke from this seat; rates/go and Stack landing belong to seat1/3.
No frozen contracts or bind_grants changed. Current: scripts/check_release.py,
51-row docs/acceptance-matrix.json, docs/ACCEPTANCE.md and14 release-check unit
controls. Matrix has no premature passed gates; candidate evidence is an index,
not a semantic coverage claim. Next: exact committed clean-archive release
measurement, post hash and review receipt.

Active owned processes: temporary cockpit QA server exec34921 at127.0.0.1:8789,
script /private/tmp/astra-web-browser-server.py, disposable synthetic state only.
Read-only mesh collectors at /private/tmp/astra-mesh-watch-s2ip5yuq/: Fable34258,
Grok original97057, Grok new82353, board23546. Active polling uses poll.py;
collectors cannot wake a finished Codex turn. No subject inference process.
