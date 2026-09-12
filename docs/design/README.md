# Design documents received from outside the build

Documents here are placed byte-identical as received and are NOT specification amendments. BUILD_SPEC rev 1.0 plus the
recorded, adopted amendments (ADR-016..018 and addenda) governs. A design becomes binding only through a reviewed
ADR or an INTERFACES amendment that names it.

| File | Received | SHA-256 | From | Status |
|---|---|---|---|---|
| `peb_cockpit_tui_design.md` | 2026-09-12 00:23 EDT (file time; handed to seat 1/3 by Anthony at 00:3x EDT: "think you can work this into the room?") | `fc7b361b0df227e0cabf54605dd16453368ef7095323e882170e6d0144f74589` | outside author (the document addresses Anthony; its `fileciteturn…` / `citeturn…` markers are the author's tool citations, not repository references) | received; under the seats' review on the board; lane assignment is Anthony's |

## Fit notes at main `4ef1a76` (seat 1/3, first read)

- The document counts 21 closed service operations; `main` carries 22 since `comparison.get` (`f5e0ac9`).
- Its DeepSeek examples name `deepseek-v4-flash`; this repository's configs and the recorded smoke use `deepseek-flash`,
  which the adapter's `GET /models` probe accepted on 2026-09-11. Model ids are never hard-coded in a cockpit (the
  document says the same); verify against the probe, do not adopt the document's name.
- Its architectural recommendation (a TUI as an authenticated client of the existing loopback web seam, so the
  hosted one-use preview rule cannot fork; a test-only in-process transport against `WorkroomService`) is consistent
  with the boundaries on `main`. Its additive service proposals (`events.since`, a commit-notification stream, a model
  artifact digest projection, `RunSummary` enrichment) are amendments if and when built, each behind its own review.
