# TUI walkthrough follow-up — ACCEPT

Seat 2/3, 2026-09-12. RE: board #28840; closes the walkthrough CHANGES in `TUI-84b2ad1-browser-walkthrough-codex.md` at `1c70bb3`.

**ACCEPT** `d72daea49b02ebdeac237f981fc3ac72dd6689fb` for the assigned browser/documentation/walkthrough scope. The browser compatibility ACCEPT for product `056edda9f022e2db210ebfac5af582ca734e9014` stands. Seat 3/3's independent verifier/inspector verdict remains separate.

An independent exact archive reran `bash scripts/walkthrough_state.sh <new-temp-parent>/custom` successfully. The supplied path is now a container: its children are exactly `state` and `study`, and its parent contains only that container. The serving root inventory reports **five runs: three completed, one waiting_review, one failed**. The partial study reports planned 8, dispatched 1, recorded 1, started 1, provider_completed 0, unknown 0. A second invocation on that nonempty container exits **2**; SHA-256 fingerprints of every existing file remain identical. Printed cleanup targets the container itself, and the printed attach command includes the same explicit state root. `bash -n scripts/walkthrough_state.sh` passes.

Artifacts: `/private/tmp/astra-walkthrough-d72daea-output.txt`, `/private/tmp/astra-walkthrough-d72daea-check.json`; exact archive `/private/tmp/astra-walkthrough-d72daea`. All demonstration state is temporary; no model or paid call was made.

README now distinguishes the browser's uncertain-outcome path from the TUI's refetch behavior. WALKTHROUGH and TUI docs explain the same-root secret lookup and distinguish serve + attach from the alternative tui --serve route. These close the requested wording corrections; integration documentation still needs actual merge/verdict references when landed.

`git diff --exit-code 84b2ad1 d72daea -- src tests` passes: no product or test delta. Accordingly the prior 145-test browser/TUI/service result and real-browser literal verified_head rendering check remain the relevant product evidence; no full-suite rerun is claimed here. Existing browser view-binding/inspector limits at #28802 remain named and unchanged. No acceptance matrix row or release status is promoted by this review.
