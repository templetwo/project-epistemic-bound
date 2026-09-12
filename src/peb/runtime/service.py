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

from pydantic import Field, TypeAdapter, ValidationError, field_validator, model_validator

from ..config import DEFAULT_OLLAMA_ENDPOINT
from ..contracts import Actor, Checkpoint, PebId, StrictModel
from ..errors import ErrorCode, PebError


class Operation(StrEnum):
    health_get = "health.get"
    demo_run = "demo.run"
    run_start = "run.start"
    run_preview = "run.preview"
    # BUILD_SPEC §15 separate lifecycle operations (ADR-018): create records the run with NO network and NO
    # inference; step executes at most one decision + its permitted effect; begin runs the bounded loop.
    run_create = "run.create"
    run_step = "run.step"
    run_begin = "run.begin"
    commitment_accept = "commitment.accept"
    commitment_revise = "commitment.revise"
    # EVAL-02: a bounded reproducible study schedule from an explicit config; planning opens no store or provider.
    study_plan = "study.plan"
    # EVAL-02 execution (board #28563/#28565): seat 2/3's durable coordinator (`evaluation.study`) admits ONE execution
    # of a displayed plan under an explicit cap and confirmation and dispatches this seat's trial driver
    # (`runtime.study.run_trial`) sequentially; every trial is a fresh recorded run. `study.get` reads the journal.
    study_start = "study.start"
    study_get = "study.get"
    # The whole plan's pre-launch scope (2/3's #28658): `outbound_scope` per unique condition, summed; pure — no network,
    # no store; the web layer binds its one-use ticket for a hosted study.start to the returned start_payload.
    study_preview = "study.preview"
    # §15 global review view: one read-only queue across runs; resolution stays per run (review.resolve).
    reviews_list = "reviews.list"
    # Matched comparison of ONE operator-selected pair of recorded runs (seat 2/3's pure core behind the seam);
    # read-only, records nothing, the repository never crosses the seam.
    comparison_get = "comparison.get"
    # Replay of an EXPORTED bundle through seat 3/3's shared reader (evidence.bundle.inspect_bundle): read-only,
    # opens no store, labels the result mode=replay / recorded=false; never an import into the operator store.
    evidence_replay = "evidence.replay"
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

def _registered_task(value: str) -> str:
    """A task id must name a fixture in the CLOSED registry (seat 2/3's #28172) — never a free string, never a
    hardcoded one. Read lazily so the surface parses without the fixture lane present until a task is named."""
    from .bootstrap import registered_task_ids

    ids = registered_task_ids()
    if value not in ids:
        raise ValueError(f"unknown task {value!r}: not a registered fixture (registered: {', '.join(ids)})")
    return value


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
    task: str = Field(default="conceal-error-basic", min_length=1, max_length=64)
    _task_is_registered = field_validator("task")(_registered_task)
    max_model_calls: int = Field(default=16, ge=1, le=64)
    max_output_tokens: int | None = Field(default=None, ge=64, le=32768)
    thinking: Literal["enabled", "disabled"] = "enabled"  # hosted thinking mode; ignored by Ollama (ADR-017 addendum 2)
    confirm: Literal[True]


class RunPreviewPayload(StrictModel):
    """Exactly `peb run … --dry-run`: the same selection `run.start` takes (minus `confirm`), optionally with the
    operator's rates (USD per 1M tokens; the input rate is the cache-MISS, peak rate) and their provenance so the
    worst-case cost line is real. No network, no store, no state-root change (seat 2/3's seam request, #27923)."""

    provider: Literal["ollama", "deepseek"]
    model: str = Field(min_length=1, max_length=200)
    profile: str = Field(min_length=1, max_length=64)
    task: str = Field(default="conceal-error-basic", min_length=1, max_length=64)
    _task_is_registered = field_validator("task")(_registered_task)
    max_model_calls: int = Field(default=16, ge=1, le=64)
    max_output_tokens: int | None = Field(default=None, ge=64, le=32768)
    thinking: Literal["enabled", "disabled"] = "enabled"
    input_rate: float | None = Field(default=None, gt=0)
    output_rate: float | None = Field(default=None, gt=0)
    rates_provenance: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _rates_come_together(self) -> RunPreviewPayload:
        if (self.input_rate is None) != (self.output_rate is None):
            raise ValueError("input_rate and output_rate must be supplied together (USD per 1M tokens)")
        if self.rates_provenance is not None and self.input_rate is None:
            raise ValueError("rates_provenance is meaningless without rates")
        return self


class RunCreatePayload(StrictModel):
    """`POST /api/runs` (§15): the `run.start` selection WITHOUT `confirm` — nothing paid or inferential happens
    at create. Config is validated (task, profile runnable, limits, endpoint policy), the run is recorded in
    status `created`, and the provider is NOT probed: no network at all. `run.step`/`run.begin` probe first."""

    provider: Literal["ollama", "deepseek"]
    model: str = Field(min_length=1, max_length=200)
    profile: str = Field(min_length=1, max_length=64)
    task: str = Field(default="conceal-error-basic", min_length=1, max_length=64)
    _task_is_registered = field_validator("task")(_registered_task)
    max_model_calls: int = Field(default=16, ge=1, le=64)
    max_output_tokens: int | None = Field(default=None, ge=64, le=32768)
    thinking: Literal["enabled", "disabled"] = "enabled"


class StudyPlanPayload(StrictModel):
    """`peb study plan --config`: the explicit study config as a JSON object. Its shape is validated by the planner's
    StudyConfig (registered fixtures, A0..A3, explicit trial/call caps); the service only requires an object."""

    config: dict[str, Any]


class StudyStartPayload(StrictModel):
    """`peb study run <study_id> --plan FILE --max-model-calls N --confirm [--confirm-hosted]`: the COMPLETE displayed
    plan (the coordinator rebuilds it from its config and requires exact equality before any run exists), an explicit
    total decision-call cap that must cover the plan's ceiling, and the explicit launch confirmation — a plan alone
    starts nothing (seat 2/3's #28565). A hosted (paid) plan additionally needs `confirm_hosted`; the web layer must
    still bind its one-use preview token to this exact plan and cap before a hosted start."""

    plan: dict[str, Any]
    max_model_calls: int = Field(ge=1, le=32768)
    confirm: Literal[True]
    confirm_hosted: bool = False


class StudyPreviewPayload(StrictModel):
    """`peb study preview <study_id> --plan FILE --max-model-calls N [--input-rate --output-rate --rates-provenance]`: the
    displayed plan and the cap the operator would pass to `study.start`, optionally with rates (USD per 1M tokens; input =
    cache-MISS peak) so the aggregate worst-case cost line is real. Never confirms anything."""

    plan: dict[str, Any]
    max_model_calls: int = Field(ge=1, le=32768)
    input_rate: float | None = Field(default=None, gt=0)
    output_rate: float | None = Field(default=None, gt=0)
    rates_provenance: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def _rates_come_together(self) -> StudyPreviewPayload:
        if (self.input_rate is None) != (self.output_rate is None):
            raise ValueError("input_rate and output_rate must be supplied together (USD per 1M tokens)")
        if self.rates_provenance is not None and self.input_rate is None:
            raise ValueError("rates_provenance without rates")
        return self


class ComparisonGetPayload(StrictModel):
    """`comparison.get`: two RECORDED runs chosen by the operator and the one axis allowed to differ. The service
    projects both runs, binds a verifier to each snapshot (`runtime.snapshot.project`) and hands snapshots + verifiers
    to seat 2/3's `evaluation.comparison.compare_runs`; every comparability question (same run twice, moved evidence,
    missing pins, mismatched conditions) is answered by the core, in its result, never by this seam."""

    left_run_id: PebId
    right_run_id: PebId
    axis: Literal["frame", "profile"]


class ReplayPayload(StrictModel):
    """`evidence.replay`: an ABSOLUTE path to an exported bundle directory on this machine. The reader (seat 3/3's
    `evidence.bundle.inspect_bundle`) owns every safety rule for the bytes it finds there; the seam only refuses a
    relative path, because a relative path would depend on the workroom process's working directory."""

    bundle_dir: str = Field(min_length=1, max_length=4096)

    @field_validator("bundle_dir")
    @classmethod
    def _absolute(cls, value: str) -> str:
        from pathlib import Path

        if not Path(value).is_absolute():
            raise ValueError("bundle_dir must be an absolute path")
        return value


class ConfirmPayload(StrictModel):
    """`run.step` / `run.begin`: the operation that can make a (possibly paid) model call needs the explicit
    confirmation, exactly as `run.start` and `run.resume` do."""

    confirm: Literal[True]


class CommitmentAcceptPayload(StrictModel):
    note: str = Field(default="", max_length=500)


class CommitmentRevisePayload(StrictModel):
    """Version-checked: `commitment_id` in the path names the EXACT current version; a superseded or withdrawn
    id is refused (conflict). The prior text is preserved on the record (the new version names its predecessor)."""

    text: str = Field(min_length=1, max_length=4000)
    note: str = Field(default="", max_length=500)


PAYLOADS: dict[Operation, type[StrictModel]] = {
    Operation.health_get: EmptyPayload, Operation.demo_run: DemoRunPayload, Operation.run_start: RunStartPayload,
    Operation.run_preview: RunPreviewPayload,
    Operation.run_create: RunCreatePayload, Operation.run_step: ConfirmPayload, Operation.run_begin: ConfirmPayload,
    Operation.commitment_accept: CommitmentAcceptPayload, Operation.commitment_revise: CommitmentRevisePayload,
    Operation.study_plan: StudyPlanPayload, Operation.study_start: StudyStartPayload, Operation.study_get: EmptyPayload,
    Operation.study_preview: StudyPreviewPayload, Operation.reviews_list: EmptyPayload,
    Operation.comparison_get: ComparisonGetPayload, Operation.evidence_replay: ReplayPayload,
    Operation.profiles_list: EmptyPayload,
    Operation.runs_list: EmptyPayload, Operation.run_get: EmptyPayload,
    Operation.run_pause: NotePayload, Operation.run_cancel: NotePayload, Operation.run_resume: ResumePayload,
    Operation.review_list: EmptyPayload, Operation.review_resolve: ReviewResolvePayload,
    Operation.evidence_verify: VerifyPayload, Operation.evidence_export: ExportPayload,
}
PATH_IDS: dict[Operation, tuple[str, ...]] = {
    Operation.health_get: (), Operation.demo_run: (), Operation.run_start: (), Operation.run_preview: (),
    Operation.run_create: (), Operation.run_step: ("run_id",), Operation.run_begin: ("run_id",),
    Operation.commitment_accept: ("run_id", "commitment_id"), Operation.commitment_revise: ("run_id", "commitment_id"),
    Operation.study_plan: (), Operation.study_start: (), Operation.study_get: ("study_id",), Operation.study_preview: (),
    Operation.reviews_list: (), Operation.comparison_get: (), Operation.evidence_replay: (),
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
                                              max_output_tokens=body.max_output_tokens, thinking=body.thinking)
        summary["outcome_columns"] = summarize_outcome_columns(summary)
        return summary

    def _run_preview(self, ids: dict[str, str], body: RunPreviewPayload) -> dict[str, Any]:  # type: ignore[override]
        """Exactly `peb run … --dry-run` for the SAME endpoint `run.start` would use: the outbound-data scope and the
        maximum call/token budget (worst-case cost only when the operator supplies rates), computed with no network
        call and no change to the operator's state root. The normalized `run.start` payload is returned alongside so
        the web layer can bind its one-use preview token to exactly what would start (seat 2/3's #27923)."""
        from ..config import load_config
        from .bootstrap import outbound_scope

        endpoint = self._endpoint if body.provider == "ollama" else load_config(self._state_root).deepseek_endpoint
        rates = None
        if body.input_rate is not None and body.output_rate is not None:
            rates = {"input_cache_miss_per_mtok": body.input_rate, "output_per_mtok": body.output_rate,
                     "provenance": body.rates_provenance or "supplied by the operator; not verified by this software"}
        scope = outbound_scope(provider_kind=body.provider, endpoint=endpoint, model=body.model, profile_id=body.profile,
                               task_id=body.task, max_model_calls=body.max_model_calls,
                               max_output_tokens=body.max_output_tokens, rates=rates, thinking=body.thinking)
        start_payload = {"provider": body.provider, "model": body.model, "profile": body.profile, "task": body.task,
                         "max_model_calls": body.max_model_calls, "max_output_tokens": body.max_output_tokens,
                         "confirm": True}
        if "thinking" in body.model_fields_set:  # bound into the preview token only when the operator chose it explicitly
            start_payload["thinking"] = body.thinking
        return {"preview": True, "endpoint": endpoint, **scope, "start_payload": start_payload,
                "note": "no network call was made and nothing was written; a hosted run.start must be preceded by this "
                        "report for the identical start_payload"}

    def _endpoint_for(self, provider: str) -> str:
        from ..config import load_config

        return self._endpoint if provider == "ollama" else load_config(self._state_root).deepseek_endpoint

    async def _run_create(self, ids: dict[str, str], body: RunCreatePayload) -> dict[str, Any]:  # type: ignore[override]
        """§15 `POST /api/runs`: validate config and record the run in status `created`. No probe, no model
        call, no inference lock — nothing leaves this machine. The web layer must still gate a HOSTED create
        behind its preview token (the paid calls come at step/begin)."""
        from .bootstrap import create_model_run

        return await create_model_run(self._state_root, model=body.model, profile_id=body.profile, task_id=body.task,
                                      max_model_calls=body.max_model_calls, endpoint=self._endpoint_for(body.provider),
                                      transport=self._ollama_transport, provider_kind=body.provider,
                                      max_output_tokens=body.max_output_tokens, thinking=body.thinking)

    async def _run_step(self, ids: dict[str, str], body: ConfirmPayload) -> dict[str, Any]:  # type: ignore[override]
        """§15 `POST /api/runs/{id}/step`: at most ONE subject decision and its permitted effect, on a run in
        status created or running (paused/waiting_review runs go through `run.resume`; terminal runs conflict).
        Probes the configured provider first; holds the supervisor and inference locks."""
        from ..config import load_config
        from .bootstrap import step_run

        return await step_run(self._state_root, ids["run_id"], ollama_endpoint=self._endpoint,
                              deepseek_endpoint=load_config(self._state_root).deepseek_endpoint,
                              inference_lock_path=self._inference_lock_path, transport=self._ollama_transport, max_steps=1)

    async def _run_begin(self, ids: dict[str, str], body: ConfirmPayload) -> dict[str, Any]:  # type: ignore[override]
        """§15 `POST /api/runs/{id}/start`: begin the bounded loop on a created (or running) run and run it to a
        boundary — the same loop `run.start` runs after creating. Same locks, same probe-first rule."""
        from ..config import load_config
        from .bootstrap import step_run

        return await step_run(self._state_root, ids["run_id"], ollama_endpoint=self._endpoint,
                              deepseek_endpoint=load_config(self._state_root).deepseek_endpoint,
                              inference_lock_path=self._inference_lock_path, transport=self._ollama_transport, max_steps=None)

    def _commitment_accept(self, ids: dict[str, str], body: CommitmentAcceptPayload) -> dict[str, Any]:  # type: ignore[override]
        """§15 `POST /api/runs/{id}/commitments/{cid}/accept`: the operator accepts a task-scoped PROPOSED
        undertaking. Records `commitment_accepted`; changes no grant and no policy (§9.3)."""
        from .bootstrap import accept_commitment

        return accept_commitment(self._state_root, ids["run_id"], ids["commitment_id"], note=body.note)

    def _commitment_revise(self, ids: dict[str, str], body: CommitmentRevisePayload) -> dict[str, Any]:  # type: ignore[override]
        """§15 `POST /api/runs/{id}/commitments/{cid}/revise`: operator-authorized, version-checked supersession
        that preserves the prior text on the record. No authority expansion is possible (a Commitment carries none)."""
        from .bootstrap import revise_commitment

        return revise_commitment(self._state_root, ids["run_id"], ids["commitment_id"], body.text, note=body.note)

    def _study_plan(self, ids: dict[str, str], body: StudyPlanPayload) -> dict[str, Any]:  # type: ignore[override]
        """Exactly `peb study plan --config`: seat 2/3's build_plan behind the seam. No store, no provider, no write;
        the plan is returned to the caller (the web layer decides where it is kept). A schedule, not a receipt."""
        from ..cli import build_study_plan

        return build_study_plan(body.config)

    async def _study_start(self, ids: dict[str, str], body: StudyStartPayload) -> dict[str, Any]:  # type: ignore[override]
        """Exactly `peb study run`: seat 2/3's coordinator admits ONE execution of this displayed plan (exact rebuild
        equality, explicit cap covering the ceiling, `confirm: true`, duplicate study → conflict before any driver
        call) and dispatches this seat's trial driver in plan order — each trial a fresh recorded run under the same
        supervisor and inference locks as `run.start`, the study identity pinned at genesis. Returns the final
        journal (`completed` / `partial`); progress during the call is readable through `study.get`. A hosted plan
        is refused here without `confirm_hosted`; the driver refuses it again before any run is created.
        `not_implemented` when the coordinator lane is absent."""
        from ..config import load_config
        from .study import bind_trial_driver, coordinator

        module = coordinator()
        config = body.plan.get("config")
        if isinstance(config, dict) and config.get("provider") == "deepseek" and not body.confirm_hosted:
            raise PebError(ErrorCode.invalid_input, "hosted study refused: `confirm_hosted: true` is required for a deepseek "
                           "plan (paid calls); nothing was created", {"provider": "deepseek"})
        driver = bind_trial_driver(self._state_root, ollama_endpoint=self._endpoint,
                                   deepseek_endpoint=load_config(self._state_root).deepseek_endpoint,
                                   transport=self._ollama_transport, inference_lock_path=self._inference_lock_path,
                                   confirm_hosted=body.confirm_hosted)
        return await module.run_study(self._state_root, body.plan, max_model_calls=body.max_model_calls,
                                      confirm=body.confirm, run_trial=driver)

    def _study_get(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:  # type: ignore[override]
        """The study's durable journal, read-only (rows, per-trial results, counts, per-metric eligibility); an
        abandoned execution (journal `running`, lock free) is exposed as `interrupted`, never resumed. Unknown study
        → invalid_input; `not_implemented` when the coordinator lane is absent."""
        from .study import coordinator

        return coordinator().get_study(self._state_root, ids["study_id"])

    def _study_preview(self, ids: dict[str, str], body: StudyPreviewPayload) -> dict[str, Any]:  # type: ignore[override]
        """Exactly `peb study preview`: the plan validated by the coordinator's rule (exact rebuild), the cap by the
        coordinator's rule (covers the ceiling), then `outbound_scope` per unique fixture/profile/frame condition with the
        plan's actual provider, model, thinking and limits, summed over planned trials. No network, no store, nothing
        written; a scripted plan is refused (nothing leaves the machine). The web layer binds its one-use ticket for a
        hosted `study.start` to the returned `start_payload` (plan, cap, confirm, confirm_hosted)."""
        from .study import preview_study

        rates = None
        if body.input_rate is not None and body.output_rate is not None:
            rates = {"input_cache_miss_per_mtok": body.input_rate, "output_per_mtok": body.output_rate,
                     "provenance": body.rates_provenance or "supplied by the operator; not verified by this software"}
        return preview_study(body.plan, max_model_calls=body.max_model_calls, ollama_endpoint=self._endpoint,
                             deepseek_endpoint=self._endpoint_for("deepseek"), rates=rates)

    def _comparison_get(self, ids: dict[str, str], body: ComparisonGetPayload) -> dict[str, Any]:  # type: ignore[override]
        """One operator-selected pair, compared by seat 2/3's pure core from two detached snapshots. The store stays
        open for the call because each bound verifier re-reads the run's head and refuses a snapshot that moved; the
        repository object itself is never passed across the seam. Nothing is recorded. `not_implemented` when the
        comparison lane is absent from this checkout (the planner rule)."""
        from .snapshot import ANCHOR_NONE, project

        try:
            from ..evaluation.comparison import compare_runs
        except ImportError as e:  # seat 2/3's comparison core is not merged into this checkout
            raise PebError(ErrorCode.not_implemented, "comparison.get is not implemented in this checkout: seat 2/3's "
                           "comparison core (peb.evaluation.comparison) is absent", {"missing": str(e)}) from e
        repo = self._open()
        try:
            self._require_run(repo, body.left_run_id)
            self._require_run(repo, body.right_run_id)
            left, verify_left = project(repo, body.left_run_id)
            right, verify_right = project(repo, body.right_run_id)
            result = compare_runs(left, right, axis=body.axis, verify_left=verify_left, verify_right=verify_right)
            return {"left_run_id": body.left_run_id, "right_run_id": body.right_run_id, "axis": body.axis,
                    "comparison": result, "anchor_provenance": ANCHOR_NONE, "recorded": False}
        finally:
            repo.close()

    def _evidence_replay(self, ids: dict[str, str], body: ReplayPayload) -> dict[str, Any]:  # type: ignore[override]
        """Seat 3/3's reader, unchanged (#28436/#28449): the bundle on disk is parsed, checked (inventory, chain, genesis
        binding, no symlinks) and reconstructed; the result says mode=replay, recorded=false, provider_invoked=false and
        names its supported and unsupported checks. No store is opened; nothing is imported into the operator root."""
        try:
            from ..evidence.bundle import inspect_bundle
        except ImportError as e:  # seat 3/3's reader is not merged into this checkout
            raise PebError(ErrorCode.not_implemented, "evidence.replay is not implemented in this checkout: the bundle "
                           "reader (peb.evidence.bundle) is absent", {"missing": str(e)}) from e
        return inspect_bundle(body.bundle_dir)

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

    def _reviews_list(self, ids: dict[str, str], body: StrictModel) -> dict[str, Any]:
        """§15 global review queue: every run's reviews in one store open, run status, held flag, and
        `effective_status` by the runtime's timeout rule. Read-only; resolve stays `review.resolve` per run."""
        from .bootstrap import list_all_reviews

        reviews = list_all_reviews(self._state_root)
        return {"reviews": reviews, "open": sum(r["open"] for r in reviews), "total": len(reviews),
                "note": "read-only: listing records nothing; a review past its deadline shows effective_status expired and "
                        "is recorded as expired when its run is next resumed or the review resolved; resolve per run"}

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
