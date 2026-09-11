# SOURCE_REGISTER — what this build is derived from (BUILD_SPEC §23)

Hashes are SHA-256 of local bytes as observed by seat 1/3 on 2026-09-11.
Private source documents are **not** committed; only this register is.

## In the repository

| File | Bytes | SHA-256 | Role |
|---|---|---|---|
| `BUILD_SPEC.md` | 88,128 | `5cbcee56cf2eb06a` … (full hash in `docs/receipts/` at first release) | Authoritative build specification, rev 1.0 |
| `TEAM_START.md` | 4,051 | `026ad2807242b9ac` … | Team startup and lane assignment by Anthony |

## Local, untracked (ignored by `.gitignore`)

| File | Bytes | SHA-256 | Note |
|---|---|---|---|
| `BUILD.md.html` | 581,875 | `d878d9000de2f240` … | ChatGPT HTML export of the spec conversation; `<title>ChatGPT</title>`; not an engineering input |

## Source documents cited by BUILD_SPEC §23 and NOT present on this seat

D0, P1, G1, C1, G2 (`Project_Epistemic_Boundary_*.docx`) and V0 (Master
Business Record) were not in the working folder. No hash is asserted. V0 is
excluded material by specification; it must never enter the repo, model
context or test data.

## Superseded

`project-epistemic-bound-spec-v1.md` (1,230 bytes, sha256
`3393c04e2195f75f3168a610221abdbba54247f2ffc14a424413e6514dfbdb32`) — a
ChatGPT executive summary that preceded the real spec; reviewed by all three
seats (board #27378, #27379) and removed from the folder by Anthony before
`BUILD_SPEC.md` landed.
