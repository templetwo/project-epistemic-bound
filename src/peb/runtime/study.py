"""Study trial driver — EVAL-02 execution, seat 1/3's half of the split (board #28563, #28565, #28598, #28655, #28658).

One planned trial becomes ONE fresh recorded run through the same composition, gate, executor, recorder and
evaluator as `peb demo` and `peb run`. Seat 2/3's durable coordinator (`peb.evaluation.study`) owns admission,
the journal, sequencing and the check of every result against the recorded manifest; this module owns what
touches the runtime: composing the run with the trial's exact condition, pinning the study identity into the
genesis-bound manifest, holding the locks, running to a boundary, evaluating from records, and reporting
lifecycle facts that are READ BACK from the record — never inferred from control flow. It never retries, never
picks a model, never resolves a review, and never contacts a hosted provider without the explicit hosted
confirmation the operator's own command passed in. `preview_study` is the pure pre-launch scope of a whole plan
(no network, no store), the study analogue of `peb run --dry-run` / `run.preview`.
"""
from __future__ import annotations

import functools
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from ..boundary.canonical import DOMAIN_SNAPSHOT, digest
from ..contracts import EventType, Limits, ProviderKind, RunMode
from ..errors import ErrorCode, PebError
from ..providers.scripted import SCRIPTED_MODEL_ID, ScriptedProvider

TrialDriver = Callable[[dict, dict], Awaitable[dict]]

# The CLOSED scripted control per fixture for a scripted_validation study (provider=scripted, model=scripted). A
# scripted study verifies the instrument under each planned A0..A3 profile text and every presentation frame; it is
# not model behaviour and is labelled so by mode. The plan cannot name a script (StudyConfig has no such field), so
# the choice is this explicit registry, pinned into the manifest as `settings.case`; a fixture with no registered
# control is refused BEFORE any run is created and the journal row says so. Extending the registry is a recorded
# change here, never a fallback.
STUDY_SCRIPTS: dict[str, str] = {
    "conceal-error-basic": "truthful-repair",
    "correction-handoff-basic": "correction-handoff",
    "authorized-useful-work-basic": "no-attempt",
}
PIN_KEYS = ("study_id", "trial_id", "pair_id", "condition_hash")
ANCHOR_NONE = "none_external_anchor_absent"
# A plan file's own bound (2/3's #28655): the decision ceiling (64 KiB) is for subject output, not for schedules. The
# largest schedule StudyConfig admits is 512 trials — about 210 KB of indented JSON — so 4 MiB covers every supported
# plan with room, and an unbounded read is still refused before parsing.
PLAN_FILE_MAX_BYTES = 4 * 1024 * 1024
TRIAL_LABEL = ("STUDY TRIAL — one fresh recorded run for one planned trial, through the same runtime, gate, executor, "
               "recorder and evaluator as `peb run`; every lifecycle fact here is read back from the record.")
HOSTED_REFUSAL = ("hosted study trial refused: a hosted (paid) provider needs the operator's explicit hosted confirmation "
                  "(`peb study run … --confirm-hosted` / study.start `confirm_hosted: true`); nothing was created or sent")
STALE_PLAN = "study plan is stale, modified or invalid; display a new plan"


class TrialRefused(PebError):
    """A refusal raised by THIS module before it calls into the runtime: nothing was created, no lock was taken, no
    provider was contacted. Only the driver's own pre-runtime checks raise it (plan/trial admission, the hosted
    confirmation, the scripted-control registry, an unrunnable profile, an unloadable script). A plain `PebError` may
    still escape the driver after a run exists — a held supervisor lock (`busy`) or a failed probe
    (`provider_unavailable`) happen before creation but are raised by the locks and the composer, and a record that
    cannot be read back after a run exists is an `evidence_failure` naming the run (2/3's counterexample, #28655) — so
    the coordinator's conservative rule (any exception = unknown outcome, stop) is right; this type only lets a later
    refinement tell the two apart with certainty."""


def coordinator():
    """Seat 2/3's durable coordinator behind the lane rule: `not_implemented` when it is not in this checkout,
    never a stand-in. Exposes create_study / execute_study / get_study / run_study (board #28565)."""
    import importlib

    try:
        module = importlib.import_module("peb.evaluation.study")
    except ImportError as e:
        raise PebError(ErrorCode.not_implemented, "study execution is not implemented in this checkout: the coordinator "
                       "lane (peb.evaluation.study) is not merged here", {"missing": str(e)}) from e
    return module


def _planner():
    try:
        from ..evaluation import planner
    except ImportError as e:
        raise TrialRefused(ErrorCode.not_implemented, "the planner lane (peb.evaluation.planner) is not in this checkout",
                           {"missing": str(e)}) from e
    return planner


def validate_displayed_plan(plan: Any) -> dict:
    """The coordinator's admission rule, available to the pure preview: the plan must equal, by canonical digest, a
    fresh rebuild from its own config — so a plan whose fixtures, profiles, ordering or caps have drifted since it was
    displayed is refused before anything is computed from it. Returns the rebuilt plan. No I/O beyond fixture and
    profile reads; nothing is written."""
    if not isinstance(plan, dict) or not isinstance(plan.get("config"), dict):
        raise PebError(ErrorCode.invalid_input, STALE_PLAN, {"reason": "plan is not an object with a config"})
    planner = _planner()
    try:
        rebuilt = planner.build_plan(json.loads(json.dumps(plan["config"], allow_nan=False)))
        if digest(DOMAIN_SNAPSHOT, plan) != digest(DOMAIN_SNAPSHOT, rebuilt):
            raise ValueError("plan differs from its current fixture/profile/config pins")
    except (ValueError, TypeError, KeyError) as e:
        raise PebError(ErrorCode.invalid_input, STALE_PLAN, {"reason": str(e)[:300]}) from None
    return rebuilt


def _admit(plan: Any, trial: Any):
    """Pure checks before any I/O: the plan's config is a valid StudyConfig, the trial is one of the plan's own rows
    (every identity field equal), the plan's mode matches its provider, and the identities the manifest will pin are
    non-empty strings. Every refusal is a `TrialRefused` (`invalid_input`); nothing has been created."""
    if not isinstance(plan, dict) or not isinstance(trial, dict):
        raise TrialRefused(ErrorCode.invalid_input, "study plan and trial must be JSON objects")
    planner = _planner()
    try:
        cfg = planner.StudyConfig.model_validate_json(json.dumps(plan.get("config"), allow_nan=False))
    except (ValueError, TypeError) as e:
        raise TrialRefused(ErrorCode.invalid_input, "study plan config is not a valid StudyConfig", {"reason": str(e)[:300]}) from None
    study_id, rows = plan.get("study_id"), plan.get("trials")
    if not isinstance(study_id, str) or not study_id.startswith("study_") or not isinstance(rows, list):
        raise TrialRefused(ErrorCode.invalid_input, "study plan lacks its study_id or its trials")
    keys = ("trial_id", "pair_id", "condition_hash", "fixture_id", "profile_id", "frame", "ordinal")
    if any(k not in trial for k in keys):
        raise TrialRefused(ErrorCode.invalid_input, "trial row lacks a required field", {"required": list(keys)})
    if not any(isinstance(r, dict) and all(r.get(k) == trial[k] for k in keys) for r in rows):
        raise TrialRefused(ErrorCode.invalid_input, "trial is not a row of this plan (an identity field differs)",
                           {"trial_id": str(trial["trial_id"])[:80]})
    if (trial["fixture_id"] not in cfg.fixture_ids or trial["profile_id"] not in cfg.profile_ids
            or trial["frame"] not in cfg.frames):
        raise TrialRefused(ErrorCode.invalid_input, "trial names a fixture, profile or frame outside the plan's config")
    expected_mode = "scripted_validation" if cfg.provider == "scripted" else "model_observation"
    if plan.get("mode") != expected_mode:
        raise TrialRefused(ErrorCode.invalid_input, "plan mode does not match its provider",
                           {"mode": str(plan.get("mode"))[:40], "expected": expected_mode})
    pins = {"study_id": study_id, **{k: trial[k] for k in ("trial_id", "pair_id", "condition_hash")}}
    if any(not isinstance(v, str) or not v for v in pins.values()):
        raise TrialRefused(ErrorCode.invalid_input, "study, trial, pair and condition identities must be non-empty strings")
    return cfg, pins


def _refused(e: PebError) -> TrialRefused:
    return TrialRefused(e.code, e.message, e.detail)


async def run_trial(state_root: str | os.PathLike[str], plan: dict, trial: dict, *, ollama_endpoint: str,
                    deepseek_endpoint: str, transport: Any = None, inference_lock_path: str | os.PathLike[str] | None = None,
                    confirm_hosted: bool = False) -> dict[str, Any]:
    """Run ONE planned trial as a fresh recorded run and report what the record says.

    - Scripted plans: the fixture's registered scripted control under the trial's REAL profile text (A0..A3), its
      frame, and the plan's call/token limits; mode scripted_validation; no inference lock (no inference happens).
    - Model plans: `compose_model_run` exactly as `peb run` (explicit model, runnable profile, real probe first, no
      fallback) under the supervisor and MacBook-wide inference locks; hosted providers only with `confirm_hosted`.
    - The four study identities are pinned into `manifest.settings` beside `consequence_hash` at genesis.
    - After the boundary: evaluation from records when the run started and reached a terminal state, chain
      verification with NO external anchor (labelled so), and the manifest read back for the coordinator's check.
    - Refusals this module makes before calling the runtime raise `TrialRefused` (nothing created). A held lock or a
      failed probe raise a plain `PebError` before creation. A failure AFTER the run exists is reported ON the run
      (recorded run_id, stored status, event-derived facts, `error` naming the failure) — unless the record itself
      cannot be read back, which raises `evidence_failure` naming the run. Nothing is retried.
    """
    cfg, pins = _admit(plan, trial)
    if cfg.provider == "deepseek" and confirm_hosted is not True:
        raise TrialRefused(ErrorCode.invalid_input, HOSTED_REFUSAL, {"provider": cfg.provider})
    from .bootstrap import _lanes, compose_model_run, compose_run
    from .locks import InferenceLock, SupervisorLock
    from .profiles import load_profile, require_runnable

    fixture_id, profile_id, frame = trial["fixture_id"], trial["profile_id"], trial["frame"]
    limits = Limits(max_model_calls=cfg.max_model_calls_per_trial, max_output_tokens=cfg.max_output_tokens)
    if cfg.provider == "scripted":
        case = STUDY_SCRIPTS.get(fixture_id)
        if case is None:
            raise TrialRefused(ErrorCode.invalid_input, f"no registered scripted control for fixture {fixture_id!r}: a "
                               "scripted study cannot stand in for it", {"registered": sorted(STUDY_SCRIPTS)})
        try:
            profile = require_runnable(load_profile(profile_id))  # the planned arm's real text, never the demo's fixed control
            _, _, _, _, _, load_script = _lanes()
            script = load_script(case)
        except PebError as e:
            raise _refused(e) from e
        with SupervisorLock(state_root):
            composed = compose_run(state_root, provider=ScriptedProvider(script), provider_kind=ProviderKind.scripted,
                                   mode=RunMode.scripted_validation, model_requested=SCRIPTED_MODEL_ID,
                                   model_resolved=SCRIPTED_MODEL_ID, profile_id=profile.profile_id, profile_text=profile.text,
                                   preaction_protocol=profile.preaction_protocol, fixture_id=fixture_id, frame=frame,
                                   limits=limits, case=case, profile_status=profile.status,
                                   profile_placeholder=profile.placeholder, arm=profile.arm, extra_settings=dict(pins))
            return await _drive(composed, pins, fixture_id=fixture_id, frame=frame, state_root=state_root)
    endpoint = ollama_endpoint if cfg.provider == "ollama" else deepseek_endpoint
    with SupervisorLock(state_root), InferenceLock(inference_lock_path):
        composed = await compose_model_run(state_root, model=cfg.model, profile_id=profile_id, task_id=fixture_id,
                                           max_model_calls=cfg.max_model_calls_per_trial, endpoint=endpoint, frame=frame,
                                           transport=transport, provider_kind=cfg.provider,
                                           max_output_tokens=cfg.max_output_tokens, thinking=cfg.thinking,
                                           extra_settings=dict(pins))
        return await _drive(composed, pins, fixture_id=fixture_id, frame=frame, state_root=state_root)


async def _drive(composed: Any, pins: dict[str, str], *, fixture_id: str, frame: str,
                 state_root: str | os.PathLike[str]) -> dict[str, Any]:
    from .bootstrap import _maybe_evaluate

    rt, run, repo = composed.runtime, composed.run, composed.repo
    run_id = run.manifest.run_id
    failure: Exception | None = None
    evaluation: dict[str, Any] | None = None
    try:
        try:
            await rt.run_bounded(run)
            started = any(e.event_type == EventType.model_request for e in repo.events(run_id))
            if started and not run.active:  # a held or paused trial stays exactly where the record says; not evaluated
                evaluation = _maybe_evaluate(repo, run_id, fixture_id=fixture_id, frame=frame)
        except Exception as e:  # noqa: BLE001 — the run exists: report the RECORD and name the failure; never retry
            failure = e
        try:
            verification = repo.verify(run_id, None)  # chain only; a checkpoint minted here would not be an external anchor
            return _from_records(repo, run_id, pins, evaluation=evaluation, verification=verification, failure=failure,
                                 state_root=state_root)
        except Exception as read_error:
            # The run exists but its record could not be read back: neither a refusal nor a report — an evidence
            # failure that NAMES the run, so the coordinator's unknown row and the operator can find it.
            raise PebError(ErrorCode.evidence_failure, "trial run exists but its record could not be read back",
                           {"run_id": run_id, "readback": type(read_error).__name__,
                            "runtime_failure": None if failure is None else type(failure).__name__}) from read_error
    finally:
        repo.close()


def _from_records(repo: Any, run_id: str, pins: dict[str, str], *, evaluation: dict[str, Any] | None, verification: Any,
                  failure: Exception | None, state_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Every lifecycle fact from the store, in the coordinator's result shape (#28565/#28598)."""
    manifest = repo.manifest(run_id)
    events = repo.events(run_id)
    requests = [e.payload for e in events if e.event_type == EventType.model_request]
    responses = [e.payload for e in events if e.event_type == EventType.model_response]
    finished = [e.payload for e in events if e.event_type == EventType.run_finished]
    status = str(repo.run_status(run_id))
    started = bool(requests)
    provider_completed = started and status == "completed" and any(p.get("status") == "completed" for p in finished)
    return {
        "label": TRIAL_LABEL, **pins,
        "run_id": run_id, "subject_session_id": manifest.subject_session_id,
        "mode": str(manifest.mode), "provider": str(manifest.provider_kind), "model_requested": manifest.model_requested,
        "model_resolved": sorted({str(r.get("model_resolved")) for r in responses if r.get("model_resolved")}),
        "status": status, "terminal_reason": str(finished[-1].get("terminal_reason")) if finished else None,
        "started": started, "provider_completed": provider_completed,
        "model_calls": len(requests), "events": len(events),
        "evaluation_present": bool(evaluation) and evaluation.get("status") == "recorded",
        "evaluation": evaluation,
        "verification": verification.model_dump(mode="json"), "anchor_provenance": ANCHOR_NONE,
        "manifest": manifest.model_dump(mode="json"),
        "error": None if failure is None else {"type": type(failure).__name__, "message": str(failure)[:200]},
        "state_root": str(state_root),
    }


def bind_trial_driver(state_root: str | os.PathLike[str], *, ollama_endpoint: str, deepseek_endpoint: str, transport: Any = None,
                      inference_lock_path: str | os.PathLike[str] | None = None, confirm_hosted: bool = False) -> TrialDriver:
    """The coordinator's `run_trial(plan, trial)` shape (#28565): this seat's runtime access bound in once by the
    operator's command; the plan and the trial are the coordinator's to hand over, one at a time, in plan order."""
    return functools.partial(run_trial, state_root, ollama_endpoint=ollama_endpoint, deepseek_endpoint=deepseek_endpoint,
                             transport=transport, inference_lock_path=inference_lock_path, confirm_hosted=confirm_hosted)


def preview_study(plan: Any, *, max_model_calls: int, ollama_endpoint: str, deepseek_endpoint: str,
                  rates: dict[str, Any] | None = None) -> dict[str, Any]:
    """`peb study preview` / service `study.preview` (2/3's #28658): the pre-launch scope of a WHOLE plan, computed the
    way `run.preview` computes one run's — `outbound_scope` per unique (fixture, profile, frame) condition with the
    plan's actual provider, model, thinking and limits — and summed over the planned trials. The plan is validated by
    the coordinator's own rule (exact rebuild equality) and the cap by the coordinator's own rule (≥ the ceiling), so a
    preview never blesses what `study.start` would refuse. No network call, no store, nothing written; readiness
    probes are separate from decision calls and none is made here. A scripted plan has no outbound scope."""
    from .bootstrap import outbound_scope

    accepted = validate_displayed_plan(plan)
    cfg = accepted["config"]
    if type(max_model_calls) is not int or not 1 <= max_model_calls <= 32768:
        raise PebError(ErrorCode.invalid_input, "an explicit decision-call cap (1..32768) is required")
    if max_model_calls < accepted["budget"]["model_calls_ceiling"]:
        raise PebError(ErrorCode.invalid_input, "execution cap cannot cover the displayed plan",
                       {"max_model_calls": max_model_calls, "model_calls_ceiling": accepted["budget"]["model_calls_ceiling"]})
    if cfg["provider"] not in ("ollama", "deepseek"):
        raise PebError(ErrorCode.invalid_input, "a scripted plan has no outbound scope: nothing leaves this machine; use "
                       "study.start directly", {"provider": cfg["provider"]})
    endpoint = ollama_endpoint if cfg["provider"] == "ollama" else deepseek_endpoint
    counts: dict[tuple[str, str, str], int] = {}
    for t in accepted["trials"]:
        key = (t["fixture_id"], t["profile_id"], t["frame"])
        counts[key] = counts.get(key, 0) + 1
    conditions = []
    for (fixture_id, profile_id, frame), n in sorted(counts.items()):
        scope = outbound_scope(provider_kind=cfg["provider"], endpoint=endpoint, model=cfg["model"], profile_id=profile_id,
                               task_id=fixture_id, max_model_calls=cfg["max_model_calls_per_trial"],
                               max_output_tokens=cfg["max_output_tokens"], frame=frame, rates=rates, thinking=cfg["thinking"])
        conditions.append({"fixture_id": fixture_id, "profile_id": profile_id, "frame": frame, "trials": n, "scope": scope})
    def total(path: Callable[[dict[str, Any]], Any]) -> int | float | None:
        values = [path(c["scope"]) for c in conditions]
        if any(v is None for v in values):
            return None
        return sum(v * c["trials"] for v, c in zip(values, conditions, strict=True))
    cost_total = total(lambda s: s["worst_case_cost"]["total_usd_worst_case"])
    aggregate = {
        "trials": len(accepted["trials"]), "conditions": len(conditions),
        "model_calls_ceiling": accepted["budget"]["model_calls_ceiling"],
        "output_tokens_ceiling": accepted["budget"]["output_tokens_ceiling"],
        "max_output_tokens_total": total(lambda s: s["budget"]["max_output_tokens_total"]),
        "max_input_tokens_total_worst_case": total(lambda s: s["budget"]["max_input_tokens_total_worst_case"]),
        "step_0_prompt_tokens_estimate_total": total(lambda s: s["outbound_per_call"]["step_0_prompt_tokens_estimate"]),
        "worst_case_cost": {"total_usd_worst_case": None if cost_total is None else round(cost_total, 4),
                            "basis": "sum over conditions of one run's worst case × planned trials of that condition",
                            **({"rates_provenance": str(rates.get("provenance", "supplied by the operator; not verified by this software"))}
                               if rates else {"note": "rates not supplied; cost not computed"})},
        "probes": "readiness probes are separate from decision calls; none was made for this preview",
    }
    return {"preview": True, "study_id": accepted["study_id"], "plan_hash": accepted["plan_hash"],
            "provider": cfg["provider"], "model": cfg["model"], "thinking": cfg["thinking"], "endpoint": endpoint,
            "endpoint_host": conditions[0]["scope"]["endpoint_host"] if conditions else None,
            "start_payload": {"plan": accepted, "max_model_calls": max_model_calls, "confirm": True,
                              "confirm_hosted": cfg["provider"] == "deepseek"},
            "conditions": conditions, "aggregate": aggregate,
            "note": "no network call was made and nothing was written; a hosted study.start must be preceded by this "
                    "report for the identical plan and cap"}
