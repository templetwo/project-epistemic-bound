"""Study trial driver — EVAL-02 execution, seat 1/3's half of the split (board #28563, #28565, #28598).

One planned trial becomes ONE fresh recorded run through the same composition, gate, executor, recorder and
evaluator as `peb demo` and `peb run`. Seat 2/3's durable coordinator (`peb.evaluation.study`) owns admission,
the journal, sequencing and the check of every result against the recorded manifest; this module owns what
touches the runtime: composing the run with the trial's exact condition, pinning the study identity into the
genesis-bound manifest, holding the locks, running to a boundary, evaluating from records, and reporting
lifecycle facts that are READ BACK from the record — never inferred from control flow. It never retries, never
picks a model, never resolves a review, and never contacts a hosted provider without the explicit hosted
confirmation the operator's own command passed in.
"""
from __future__ import annotations

import functools
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

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
TRIAL_LABEL = ("STUDY TRIAL — one fresh recorded run for one planned trial, through the same runtime, gate, executor, "
               "recorder and evaluator as `peb run`; every lifecycle fact here is read back from the record.")
HOSTED_REFUSAL = ("hosted study trial refused: a hosted (paid) provider needs the operator's explicit hosted confirmation "
                  "(`peb study run … --confirm-hosted` / study.start `confirm_hosted: true`); nothing was created or sent")


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


def _admit(plan: Any, trial: Any):
    """Pure checks before any I/O: the plan's config is a valid StudyConfig, the trial is one of the plan's own rows
    (every identity field equal), the plan's mode matches its provider, and the identities the manifest will pin are
    non-empty strings. Every refusal is `invalid_input`; nothing has been created."""
    if not isinstance(plan, dict) or not isinstance(trial, dict):
        raise PebError(ErrorCode.invalid_input, "study plan and trial must be JSON objects")
    try:
        from ..evaluation.planner import StudyConfig
    except ImportError as e:
        raise PebError(ErrorCode.not_implemented, "the planner lane (peb.evaluation.planner) is not in this checkout",
                       {"missing": str(e)}) from e
    try:
        cfg = StudyConfig.model_validate_json(json.dumps(plan.get("config"), allow_nan=False))
    except (ValueError, TypeError) as e:
        raise PebError(ErrorCode.invalid_input, "study plan config is not a valid StudyConfig", {"reason": str(e)[:300]}) from None
    study_id, rows = plan.get("study_id"), plan.get("trials")
    if not isinstance(study_id, str) or not study_id.startswith("study_") or not isinstance(rows, list):
        raise PebError(ErrorCode.invalid_input, "study plan lacks its study_id or its trials")
    keys = ("trial_id", "pair_id", "condition_hash", "fixture_id", "profile_id", "frame", "ordinal")
    if any(k not in trial for k in keys):
        raise PebError(ErrorCode.invalid_input, "trial row lacks a required field", {"required": list(keys)})
    if not any(isinstance(r, dict) and all(r.get(k) == trial[k] for k in keys) for r in rows):
        raise PebError(ErrorCode.invalid_input, "trial is not a row of this plan (an identity field differs)",
                       {"trial_id": str(trial["trial_id"])[:80]})
    if (trial["fixture_id"] not in cfg.fixture_ids or trial["profile_id"] not in cfg.profile_ids
            or trial["frame"] not in cfg.frames):
        raise PebError(ErrorCode.invalid_input, "trial names a fixture, profile or frame outside the plan's config")
    expected_mode = "scripted_validation" if cfg.provider == "scripted" else "model_observation"
    if plan.get("mode") != expected_mode:
        raise PebError(ErrorCode.invalid_input, "plan mode does not match its provider",
                       {"mode": str(plan.get("mode"))[:40], "expected": expected_mode})
    pins = {"study_id": study_id, **{k: trial[k] for k in ("trial_id", "pair_id", "condition_hash")}}
    if any(not isinstance(v, str) or not v for v in pins.values()):
        raise PebError(ErrorCode.invalid_input, "study, trial, pair and condition identities must be non-empty strings")
    return cfg, pins


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
    - A refusal before creation is a `PebError`. A failure AFTER the run exists is reported on the run: the recorded
      run_id, the stored status and the event-derived facts, with `error` naming the failure; nothing is retried.
    """
    cfg, pins = _admit(plan, trial)
    if cfg.provider == "deepseek" and confirm_hosted is not True:
        raise PebError(ErrorCode.invalid_input, HOSTED_REFUSAL, {"provider": cfg.provider})
    from .bootstrap import _lanes, compose_model_run, compose_run
    from .locks import InferenceLock, SupervisorLock
    from .profiles import load_profile, require_runnable

    fixture_id, profile_id, frame = trial["fixture_id"], trial["profile_id"], trial["frame"]
    limits = Limits(max_model_calls=cfg.max_model_calls_per_trial, max_output_tokens=cfg.max_output_tokens)
    if cfg.provider == "scripted":
        case = STUDY_SCRIPTS.get(fixture_id)
        if case is None:
            raise PebError(ErrorCode.invalid_input, f"no registered scripted control for fixture {fixture_id!r}: a scripted "
                           "study cannot stand in for it", {"registered": sorted(STUDY_SCRIPTS)})
        profile = require_runnable(load_profile(profile_id))  # the planned arm's real text, never the demo's fixed control
        _, _, _, _, _, load_script = _lanes()
        script = load_script(case)
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
            if failure is not None:  # the record cannot even be read back: the runtime failure is the honest report
                raise failure from read_error
            raise
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
