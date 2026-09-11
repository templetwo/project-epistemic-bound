# Provider re-review — seat 2/3

Author: seat 1/3. Reviewer: seat 2/3. Verdict: ACCEPT for #27918/#27952.
Exact provider commit: `953921e7d18d704da5e89538d655f97089321088`.
Exact independent test source: `7851d70818c25a235f520aaa1c5ff678b7d74e84`.

Fresh git archive of the provider commit, with the 29-case test file copied from
that exact test commit. Command: `uv run --locked pytest
tests/adversarial/test_hosted_provider_boundary.py -q
--junitxml=/private/tmp/astra-953921e-adversarial.xml`.
Measured 29 passed, 0 skipped, 0 failed, exit 0. JUnit SHA256:
`107d4ee55b078adf3b1d87dae8cb22c8e87383a30daee3255a18c7de7296f406`.

Whole synthetic credential reflections in both ordinary and outer JSON escaped
completion content are rejected before event/export retention, for stop and
length completions. Malformed catalog/error bodies produce typed failures;
redirects stay at the approved destination and are not followed. All transport
was mocked; no real credential or paid request was involved.

Raw and decoded scans are complementary. Recursion is bounded at eight; split,
partial and more deeply encoded reflections are explicitly outside this review's
claim. This is not universal secret detection or whole-release acceptance.
Board #27985 records the measured acceptance and exact merge pair.
