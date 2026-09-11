"""S4 operator service seam (docs/INTERFACES.md §15; board #27620/#27633). Seat 1/3.

The web layer (seat 2/3, `web/`) maps FIXED routes onto `WorkroomService.request(operation, path_ids,
payload)`. `Operation` is closed; unknown names, unexpected path ids and unknown payload fields are
`invalid_input` before any store is opened. Every operation goes through the same bootstrap functions
the CLI uses, so the UI and `peb …` cannot disagree. Nothing here is subject-visible, and no model is
called except by `run.resume`, which requires `confirm: true` and is the same explicit act as `peb resume`.
Failures are `PebError` envelopes; `not_implemented` is a real error, never a fake successful control.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import os
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from ..config import DEFAULT_OLLAMA_ENDPOINT
from ..contracts import Actor, Checkpoint, PebId, StrictModel
from ..errors import ErrorCode, PebError


class Operation(StrEnum):
    health_get = "health.get"
    demo_run = "demo.run"
    run_start = "run.start"
    profiles_list = "profiles.list"
    runs_list = "runs.list"
    run_get = "run.get"
    run_pause = "run.pause"
    run_cancel = "run.cancel"
    run_resume = "run.resume"
    review_list = "review.list"
    review_resolve = "review.resolve"
    evidence_verify = "evidence.verify"
    evidence_export = "evidence.export"


# ----------------------------------------------------------------------------- payloads (strict, closed)

class EmptyPayload(StrictModel):
    pass


class NotePayload(StrictModel):
    note: str = Field(default="", max_length=500)


class ResumePayload(StrictModel):
    confirm: Literal[True]
    model: str | None = Field(default=None, max_length=200)


class ReviewResolvePayload(StrictModel):
    decision: Literal["ack", "allow", "deny"]
    note: str = Field(default="", max_length=500)
    scripted_reviewer: bool = False  # labels the resolver for a local demo; NOT human review (§13)


class VerifyPayload(StrictModel):
    checkpoint: Checkpoint | None = None  # operator-RETAINED; None → external anchor absent (never minted here)


class ExportPayload(StrictModel):
    out: str = Field(min_length=1, max_length=1000)


class DemoRunPayload(StrictModel):
    case: Literal["truthful-repair", "authorized-concealment", "forbidden-export"]
    frame: Literal["ordinary", "game", "roleplay", "evaluation"] = "ordinary"


class RunStartPayload(StrictModel):
    """Exactly `peb run`: an explicit installed model id, an explicit profile, a bounded call budget, and an
    explicit confirmation. The service never chooses, pulls or falls back to a model."""

    provider: Literal["ollama", "deepseek"]
    model: str = Field(min_length=1, max_length=200)
    profile: str = Field(min_length=1, max_length=64)
    task: Literal["conceal-error-basic"] = "conceal-error-basic"
    max_model_calls: int = Field(default=16, ge=1, le=64)
    max_output_tokens: int | None = Field(default=None, ge=64, le=32768)
    confirm: Literal[True]


PAYLOADS: dict[Operation, type[StrictModel]] = {
    Operation.health_get: EmptyPayload, Operation.demo_run: DemoRunPayload, Operation.run_start: RunStartPayload,
    Operation.profiles_list: EmptyPayload,
    Operation.runs_list: EmptyPayload, Operation.run_get: EmptyPayload,
    Operation.run_pause: NotePayload, Operation.run_cancel: NotePayload, Operation.run_resume: ResumePayload,
    Operation.review_list: EmptyPayload, Operation.review_resolve: ReviewResolvePayload,
    Operation.evidence_verify: VerifyPayload, Operation.evidence_export: ExportPayload,
}
PATH_IDS: dict[Operation, tuple[str, ...]] = {
    Operation.health_get: (), Operation.demo_run: (), Operation.run_start: (),
    Operation.profiles_list: (),
    Operation.runs_list: (), Operation.run_get: ("run_id",), Operation.run_pause: ("run_id",),
    Operation.run_cancel: ("run_id",), Operation.run_resume: ("run_id",), Operation.review_list: ("run_id",),
    Operation.review_resolve: ("run_id", "review_id"), Operation.evidence_verify: ("run_id",),
    Operation.evidence_export: ("run_id",),
}
_ID = TypeAdapter(PebId)


def parse_request(operation: Any, path_ids: Any, payload: Any) -> tuple[Operation, dict[str, str], StrictModel]:
    """Closed operation, exact path ids (validated as PebIds), strict payload — all before any store I/O."""
    try:
        op = Operation(str(operation))
    except ValueError:
        raise PebError(ErrorCode.invalid_input, "unknown operation",
                       {"operation": str(operation)[:80], "known": [o.value for o in Operation]}) from None
    if not isinstance(path_ids, dict) or set(path_ids) != set(PATH_IDS[op]):
        raise PebError(ErrorCode.invalid_input, "path ids do not match the operation",
                       {"operation": op.value, "expected": list(PATH_IDS[op]),
                        "got": sorted(path_ids) if isinstance(path_ids, dict) else type(path_ids).__name__})
    ids: dict[str, str] = {}
    for key, value in path_ids.items():
        try:
            ids[key] = _ID.validate_python(value)
        except ValidationError:
            raise PebError(ErrorCode.invalid_input, f"{key} is not a well-formed id", {"field": key}) from None
    if not isinstance(payload, dict):
        raise PebError(ErrorCode.invalid_input, "payload must be a JSON object", {"got": type(payload).__name__})
    try:
        body = PAYLOADS[op].model_validate_json(json.dumps(payload))
    except (ValidationError, TypeError, ValueError) as e:
        detail = e.errors(include_url=False) if isinstance(e, ValidationError) else [{"msg": str(e)[:200]}]
        raise PebError(ErrorCode.invalid_input, f"invalid payload for {op.value}",
                       {"errors": [{"loc": list(map(str, d.get("loc", ()))), "type": d.get("type"), "msg": str(d.get("msg", ""))[:200]}
                                   for d in detail][:10]}) from None
    return op, ids, body


def _json_ready(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _json_ready(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(v) for v in value]
    if isinstance(value, StrEnum):
        return str(value)
    return value


def _event_ref(ev: Any) -> dict[str, Any]:
    return {"seq": ev.seq, "type": str(ev.event_type), "event_id": ev.event_id}


# ----------------------------------------------------------------------------- the service

class WorkroomService:
    """Operator-side facade over the runtime, opened per request against one state root."""

    def __init__(self, state_root: str | os.PathLike[str], *, ollama_endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
                 inference_lock_path: str | os.PathLike[str] | None = None, ollama_transport: Any = None) -> None:
        self._state_root = state_root
        self._endpoint = ollama_endpoint
        self._inference_lock_path = inference_lock_path
        # Test seam only: an httpx transport for the Ollama adapter (fake loopback server in tests).
        # `peb serve` never sets it; a real run always talks to the configured loopback endpoint.
        self._ollama_transport = ollama_transport

    async def request(self, operation: Any, path_ids: Any, payload: Any) -> dict[str, Any]:
        op, ids, body = parse_request(operation, path_ids, payload)
        handler = getattr(self, "_" + op.name)
        result = handler(ids, body)
        if inspect.isawaitable(result):
            result = await result
        return result

    # -- store access -----------------------------------------------------------------------------

    def _open(self):
        from .bootstrap import _lanes

        _, _, Repository, _, _, _ = _lanes()  # not_implemented when the boundary lane is absent
        return Repository.open(self._state_root)

    def _require_run(self, repo: Any, run_id: str) -> None:
        if not repo.run_exists(run_id):
            raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})

    # -- operations -------------------------------------------------------------------------------

    def _health_get(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:
        """The `peb doctor` report, unchanged: versions, state root, storage, port, provider readiness. No writes
        beyond what doctor itself does (it may create the state root directory)."""
        from ..cli import doctor_report
        from ..config import load_config

        cfg = dataclasses.replace(load_config(self._state_root), ollama_endpoint=self._endpoint)
        return doctor_report(cfg)

    async def _demo_run(self, ids: dict[str, str], body: DemoRunPayload) -> dict[str, Any]:  # type: ignore[override]
        """Exactly `peb demo --provider scripted --case <case>`: the same bootstrap path, the same summary."""
        from .bootstrap import run_scripted_demo, summarize_outcome_columns

        summary = await run_scripted_demo(self._state_root, body.case, frame=body.frame)
        summary["outcome_columns"] = summarize_outcome_columns(summary)
        return summary

    async def _run_start(self, ids: dict[str, str], body: RunStartPayload) -> dict[str, Any]:  # type: ignore[override]
        """Exactly `peb run --provider ollama --model … --profile … --task … --max-model-calls …`: the same bounded
        runtime path under the same supervisor and inference locks; the model id comes from the operator."""
        from ..config import load_config
        from .bootstrap import run_model_observation, summarize_outcome_columns

        endpoint = self._endpoint if body.provider == "ollama" else load_config(self._state_root).deepseek_endpoint
        summary = await run_model_observation(self._state_root, model=body.model, profile_id=body.profile,
                                              task_id=body.task, max_model_calls=body.max_model_calls,
                                              endpoint=endpoint, inference_lock_path=self._inference_lock_path,
                                              transport=self._ollama_transport, provider_kind=body.provider,
                                              max_output_tokens=body.max_output_tokens)
        summary["outcome_columns"] = summarize_outcome_columns(summary)
        return summary

    def _profiles_list(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:
        """§15.1 `GET /api/profiles`: versioned candidate and control configurations with source/status labels,
        plus the EVAL-03 hygiene findings so the UI can show why an arm is or is not runnable. No store."""
        from .profiles import check_arm_hygiene, profile_catalog

        return {"profiles": profile_catalog(), "hygiene_findings": check_arm_hygiene(),
                "note": "a profile is configuration, not law (ADR-006); [PLACEHOLDER] text is never the source contract"}

    def _runs_list(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:
        repo = self._open()
        try:
            return {"runs": [_json_ready(r) for r in repo.list_runs()]}
        finally:
            repo.close()

    def _run_get(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:
        from .reconstruct import held_proposals_from_events
        from .snapshot import read_only_run

        repo = self._open()
        try:
            rid = ids["run_id"]
            self._require_run(repo, rid)
            snap = read_only_run(repo, rid)
            held = held_proposals_from_events(rid, snap.events, snap.reviews, policy_version=repo.policy_version(rid),
                                              initial_session=snap.manifest.subject_session_id)
            return {"run": snap.model_dump(mode="json"), "status": str(repo.run_status(rid)),
                    "reviews": [r.model_dump(mode="json") for r in snap.reviews],
                    "held": {review_id: h.proposal.proposal_id for review_id, h in held.items()}}
        finally:
            repo.close()

    def _run_pause(self, ids: dict[str, str], body: NotePayload) -> dict[str, Any]:  # type: ignore[override]
        return self._control(ids["run_id"], "pause", body.note)

    def _run_cancel(self, ids: dict[str, str], body: NotePayload) -> dict[str, Any]:  # type: ignore[override]
        return self._control(ids["run_id"], "cancel", body.note)

    def _control(self, run_id: str, which: str, note: str) -> dict[str, Any]:
        from .controls import cancel_run, pause_run

        repo = self._open()
        try:
            self._require_run(repo, run_id)
            ev = pause_run(repo, run_id, by=Actor.operator) if which == "pause" else cancel_run(repo, run_id, by=Actor.operator)
            return {"run_id": run_id, "requested": which, "status": str(repo.run_status(run_id)), "event": _event_ref(ev),
                    "note": note}
        finally:
            repo.close()

    async def _run_resume(self, ids: dict[str, str], body: ResumePayload) -> dict[str, Any]:  # type: ignore[override]
        from .bootstrap import resume_run

        rid = ids["run_id"]
        if body.model is not None:
            repo = self._open()
            try:
                self._require_run(repo, rid)
                requested = repo.manifest(rid).model_requested
            finally:
                repo.close()
            if requested != body.model:
                raise PebError(ErrorCode.conflict, "a run resumes under the model it was created with",
                               {"run_id": rid, "manifest_model": requested, "requested": body.model})
        return await resume_run(self._state_root, rid, endpoint=self._endpoint,
                                inference_lock_path=self._inference_lock_path)

    def _review_list(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:
        from .bootstrap import list_reviews

        return {"run_id": ids["run_id"], "reviews": list_reviews(self._state_root, ids["run_id"])}

    def _review_resolve(self, ids: dict[str, str], body: ReviewResolvePayload) -> dict[str, Any]:  # type: ignore[override]
        from .bootstrap import resolve_review_from_records

        by = Actor.scripted_reviewer if body.scripted_reviewer else Actor.operator
        return resolve_review_from_records(self._state_root, ids["run_id"], ids["review_id"], body.decision,
                                           by=by, note=body.note)

    def _evidence_verify(self, ids: dict[str, str], body: VerifyPayload) -> dict[str, Any]:  # type: ignore[override]
        from .snapshot import ANCHOR_NONE, ANCHOR_RETAINED

        repo = self._open()
        try:
            rid = ids["run_id"]
            self._require_run(repo, rid)
            result = repo.verify(rid, body.checkpoint)  # retained checkpoint or None — never minted here (#27644)
            return {"run_id": rid, "verification": result.model_dump(mode="json"),
                    "anchor_provenance": ANCHOR_RETAINED if body.checkpoint is not None else ANCHOR_NONE}
        finally:
            repo.close()

    def _evidence_export(self, ids: dict[str, str], body: ExportPayload) -> dict[str, Any]:  # type: ignore[override]
        try:
            from ..evidence.export import export_run  # seat 3/3
        except ImportError as e:
            raise PebError(ErrorCode.not_implemented, "evidence export is not available in this checkout: the boundary "
                           "lane's exporter is not merged here", {"missing": str(e)}) from e
        repo = self._open()
        try:
            rid = ids["run_id"]
            self._require_run(repo, rid)
            bundle = export_run(repo, rid, body.out)
            return {"run_id": rid, "exported": str(bundle)}
        finally:
            repo.close()
