# Study-plan cockpit review — seat 1/3 (integrator)

Reviewed: `68eeb1585007a5f062c32c91c657d40836106086` (on main dfb1791). Verdict: ACCEPT. Reviewed at 2026-09-11T23:16-0400.

Held: the only server change is one route (`POST /api/studies/plan` → `study.plan`) through the existing authenticated, CSRF-checked binding; the page builds the config from the operator's selections (six families, four frames, A0–A3, explicit model/thinking/seed/caps), shows the backend schedule with zero outcome counts, ceilings and hashes, and downloads the same JSON; selection changes invalidate a shown plan; an over-cap config is refused with no run created; there is no execution control and no implied launch. Trial merge on main dfb1791: no conflicts; ruff clean; 559 passed / 0 skipped / 0 failed (29 web tests). Study execution remains unbuilt, as 2/3 states.
