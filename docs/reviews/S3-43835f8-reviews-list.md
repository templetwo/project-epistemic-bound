# Review — 43835f8 global reviews.list (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `43835f858b80320a57d729aebaf77f895afc2f0e` on `build/claude-core`.  
**Verdict:** **ACCEPT.**

## Store / ISO-02

Uses `list_runs()` (3/3 public). One store open. Reviews from `reviews_from_events` (recorded). `effective_status` applies expire_reviews **read-only** (`expired` when open and past deadline); listing writes nothing (event count unchanged). Resolve stays `(run_id, review_id)` via `review.resolve`. Tests on `tmp_path`. **Pass.**

## Export (this seat, separate)

`reviews.json` was `[]`. That is 3/3's item (#28286), not a reject of 43835f8. Export uses recorded status only — it does **not** copy `effective_status` into the bundle.
