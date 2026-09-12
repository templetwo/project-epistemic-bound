# Study plan seam review — seat 2/3

ACCEPT `1178d6f5a9891cd0a712b312e17551fd2fa65090` (parent main `185ac6d`).
Read the exact CLI, service and test diff. Measured an isolated git archive:
`uv run --locked pytest -q tests/evaluation/test_planner.py tests/runtime/test_service.py tests/unit/test_cli_bootstrap.py --junitxml=/private/tmp/astra-study-seam-1178d6f.xml`:
79 passed, zero skipped, zero failed; changed-file Ruff clean. JUnit SHA256:
302e740c2a8beb830e0f061b8582d28ad30184d5ebc5031b211f35a73e214be3.

The service uses the same pure build_plan contract with strict config validation,
explicit caps and zero initial outcomes. Independent checks establish exact
service/core object equality and no state-root creation; a patched socket connect
raises if planning tries networking and was never reached. An existing output
containing a sentinel remained byte-identical after the CLI returned conflict.
Exclusive file creation also protects against overwrite races. The unsupported
study run operation stays explicit; planning does not authorize or start trials.

Minor CLI robustness follow-up: filesystem errors arising after path prechecks
(e.g. an output appearing concurrently or a dangling symlink) currently surface
as OSError rather than a PebError envelope. They cannot overwrite the file because
creation remains exclusive. This does not block the planning seam ACCEPT.
