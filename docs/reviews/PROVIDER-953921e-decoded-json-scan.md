# Review — decoded-JSON credential scan at 953921e (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, provider-boundary owner.  
**Reviewed:** `953921e7d18d704da5e89538d655f97089321088` on `build/claude-core` (parent `ed663ac`).  
**Verdict:** **ACCEPT.** #27959 hold is lifted for this hash. The smoke's reviewed commit may move from `0079a37` to `953921e` (or its `--no-ff` merge with 2/3's expanded controls). `ed663ac` remains not the pin.

## What #27952 needed

`ed663ac` scanned raw bytes only. A whole-key reflection written as JSON `\uXXXX` is absent from the wire bytes; `r.json()` then puts the exact key in `content` (or a catalog id, or an error message). That is a full credential in the record, not a partial.

## Matcher

`_reflects_key`: exact key in raw UTF-8 **or** `_contains_secret(r.json(), key)`. Still refuse-whole (`content=""`, unresolved model, no catalog), still `credential_reflected`, still one increment of the usage counter. Probe and generate, any status, before anything leaves the adapter.

`_contains_secret` (depth-bounded at 8):

- strings: exact substring of the decoded value, then if the string looks like JSON (`{` / `[` / `"`) `json.loads` and recurse
- dict: keys and values
- list: items
- split/partial: out of scope; tested (`KEY[:20]` / `KEY[20:]` is not a hit)

Tests cover outer-level `\uXXXX` in content (stop/length), nested escaping inside the decision document (stop/length), escaped catalog id, escaped error message, exactness, and bound (found at 3 nested document-decodes; not found at 12). Growth of the bound fixture is ~2x/level; the 6x build that OOM'd the first suite is in the commit message, not in the tree.

## Depth bound

`if depth > 8: return False`. Structural nesting and JSON-in-string nesting share the counter. A chat-completions body is ~5 levels to `content`; one extra `json.loads` of that content is the realistic case. 8 is enough for this API. Residual, not CHANGES: a 9-deep *object* leaf that is the key, or 9 nested JSON-document wraps, would not be found. That is the bound working, not a miss of #27952.

## Usage visibility

Unchanged and still enough: `credential_reflected` count; generate attempted/received as at `ed663ac`; durable `model_response.error`.

## Not this seat

2/3 re-runs the expanded 29 controls and posts that hash. This ACCEPT is the adapter. No paid smoke. No `bind_grants`.
