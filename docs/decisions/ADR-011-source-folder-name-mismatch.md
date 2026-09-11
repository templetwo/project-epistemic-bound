# ADR-011 — Source folder name mismatch at S0

Status: accepted by seat 1/3, 2026-09-11 ~05:00 EDT. BUILD_SPEC §4.1 expected `~/Desktop/untitled`; the actual folder was `~/Desktop/untitled folder` (with a space). Every other §4.1 check passed (not a repo, not a symlink, BUILD_SPEC.md present, destination absent). Decision: treat the actual folder as SRC and run the rest of §4.1 unchanged (`mv -n`, `git init -b main`). Bounded per §0: no overwrite risk, reversible by a second move. Receipt: board entries #27404, #27406.
