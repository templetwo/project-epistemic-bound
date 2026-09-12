# Review — 200fb48 genesis prefix (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `200fb48dc902c3d9ff059c93637d8e57323002fa`.  
**Verdict:** **ACCEPT.** #28526/#28530 closed from this seat.

At cursor 0, first event must be `seq==0`, `event_type==run_created`, `prev_hash is None` (plus existing contiguity, links, identity, no-shrink). Tests: `[seq=2 run_created …]` resync; `[seq=0 model_request]` resync; genesis with a `prev_hash` resync; real genesis appends. Older model tests moved to zero-based genesis. App/CLI remainder still 2/3.
