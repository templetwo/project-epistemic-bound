# Review — 7816d14 TUI slice 1 sanitizer + verification badge (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `7816d14ec7424a8bcbc90f1f0a91222ca66cdefe` (sanitizer + `VerificationBadge` only). Transport/UI remainder is 2/3 and 1/3.  
**Verdict:** **ACCEPT** this evidence-display slice.

## Sanitizer

`display()` maps C0/C1/DEL and listed invisible/bidi controls to visible pictures; ESC cannot survive as a control. The design's OSC-52 string is a verbatim test. Bounded length. Non-strings go through `str()` then the same table. **Pass.** Slice 2 must actually *call* `display()` on model/reasoning/commitment/resource/error strings before they hit the screen.

## VerificationBadge

Pinned to the `Head` it verified. `label()` shows the verifier's own `summary` (`chain_consistent; external_anchor_absent` is never rewritten as "verified"). When the head moves: STALE, verify again. Failed chain → critical alert. Usage `None` stays `None`. Recorded ≠ started (`model_request` count). Nothing here writes evidence. **Pass.**

## Note

`apply_verification` takes whatever dict the seam returns. When `evidence.replay` lands, the TUI must pin the badge to `inspect_bundle`'s `verification.summary` the same way, still never treating imported replay as a stored run.
