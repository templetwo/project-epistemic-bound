# Seat 2/3 review — study driver and preview 19d6d28

Verdict: ACCEPT `19d6d28`. This closes #28655's CLI plan-reader finding and
qualifies the prior pre-creation-error claim with the measured counterexample.

Exact archive validation: 45 driver/seam/CLI/coordinator targeted tests passed,
zero failed, zero skipped; scoped Ruff passed. Independent reproduction round-trips
the original valid 480-trial, 196,093-byte plan. The reader now limits bytes before
parsing under a separate 4 MiB bound; strict malformed/oversized controls pass.

The readback-failure control now returns an evidence_failure exception naming the
already-recorded run. Generic exceptions remain unknown to the coordinator;
TrialRefused is a distinct optional pre-runtime classification, not a reason to
reinterpret all PebError instances. No retries are introduced.

Independent pure-preview control: 24 hosted-plan trials, eight frame/profile
conditions with three repeats each; every scope preserves its planned frame,
aggregate output ceiling equals 24 * 8 * 512, normalized start_payload exactly
matches the complete accepted plan/cap/confirm/confirm_hosted request, and absent
rates yield unknown cost. Patched socket.connect was never called. The helper
composes and discards temporary state; purity here means no provider call or
operator-state change, not zero temporary filesystem activity.

The explicit three-fixture scripted registry remains a declared execution limit.
The other three families are refused in scripted mode. No broader S5 completion,
model behavior, paid smoke or release verdict is implied. Owner's full690 pass
count is separate from this seat's targeted45 measurement.
