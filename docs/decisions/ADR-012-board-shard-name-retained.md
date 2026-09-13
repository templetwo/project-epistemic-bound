# ADR-012 — Board shard name retained after rename

Status: accepted by seat 1/3, 2026-09-11. The t2helix cross-seat board shard stays `colab-untitled-folder` after the folder became `project-epistemic-bound`. Reason: seat watchers filter on the exact string (board #27388); a mid-build rename would blind them silently. The name is an address, not a description. Revisit only at a stage boundary with all seats acking on both shards.

**Addendum, 2026-09-12 (seat 1/3).** The room closed; no seat watcher filters on this string any
more, so the original reason has lapsed. The decision stands on a second, stronger footing: the
shard is the address of the closed record — board ids #27353 onward are cited by `docs/HANDOFF.md`,
`docs/reviews/` and the receipts, and a rename would orphan every one of those citations. The
revisit condition above is unreachable and is retired; the name is permanent unless Anthony rules
otherwise.
