# Seat 2/3 review — bf7f9ad

ACCEPT the evidence.replay delta at bf7f9adff0ba2c9b5b6b4414d636bfd53d7114b1.
It validates an absolute path and returns inspect_bundle unchanged. It opens no
operator repository and preserves failed inspection reports. Relative/missing/
extra-key inputs are rejected; absent reader reports not_implemented.

Exact bf7f9ad archive: 71 service tests passed, zero failed/skipped. JUnit
/private/tmp/astra-replay-seam-bf7f9ad.xml. Composed archive bf7f9ad + reader94442bb
+ draft web binding: 33 HTTP tests passed, including a real scripted export,
reconstruction, corrupted checksum refusal, unchanged run/inventory and auth/CSRF.
JUnit /private/tmp/astra-replay-ui-http.xml. The latter is not an exact commit.

This accepts the replay seam delta only. Its ancestor TUI transport7816d14 still
requires the mutation ambiguity/invalid-success fixes recorded at #28469.
