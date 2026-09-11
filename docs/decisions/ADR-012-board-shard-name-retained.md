# ADR-012 — Board shard name retained after rename

Status: accepted by seat 1/3, 2026-09-11. The t2helix cross-seat board shard stays `colab-untitled-folder` after the folder became `project-epistemic-bound`. Reason: seat watchers filter on the exact string (board #27388); a mid-build rename would blind them silently. The name is an address, not a description. Revisit only at a stage boundary with all seats acking on both shards.
