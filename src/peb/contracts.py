"""Frozen v0.1 contracts (BUILD_SPEC §8). Owner: seat 1/3. Changes require a reviewed
interface amendment; nobody silently changes another lane's contracts (§3.1).

Rules (§8): JSON-compatible values, schema_version 1, collision-resistant IDs, UTC
timestamps, explicit status enums. Unknown fields fail validation. No coercion of
"false" into a boolean. Duplicate JSON keys and NaN/Infinity are rejected by
`parse_strict` before a model ever sees the bytes.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
)

SCHEMA_VERSION = 1


def _exact_json_integer(v: object) -> object:
    """`Literal[1]` matches by equality, so JSON `true` and `1.0` would normalise to 1. Require the
    exact integer type (defect found by seat 2/3, 2026-09-11)."""
    if type(v) is not int:
        raise ValueError("schema_version must be the JSON integer 1 (not a boolean, float or string)")
    return v


SchemaVersion = Annotated[Literal[1], BeforeValidator(_exact_json_integer)]

# ----------------------------------------------------------------------------- scalars

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
# Resource IDs: small validated grammar; never a host path, never a SQL fragment (§10).
ResourceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]*(\.[a-z0-9_-]+){0,3}$", max_length=64)]
# Supervisor-issued IDs: <prefix>_<32 hex>. Human-readable grant slugs are also allowed for grants.
PebId = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,8}_[0-9a-f]{32}$")]
GrantId = Annotated[str, StringConstraints(pattern=r"^(grant\.[a-z0-9][a-z0-9-]{0,62}|grnt_[0-9a-f]{32})$")]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")]

DECISION_CONTENT_CEILING_BYTES = 64 * 1024  # §9.1


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    """Every contract record: unknown fields fail, no type coercion, immutable."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# ----------------------------------------------------------------------------- enums

class ProviderKind(StrEnum):
    scripted = "scripted"
    ollama = "ollama"


class RunMode(StrEnum):
    replay = "replay"
    scripted_validation = "scripted_validation"
    model_observation = "model_observation"


class RunStatus(StrEnum):
    created = "created"
    running = "running"
    waiting_review = "waiting_review"
    paused = "paused"
    completed = "completed"
    declined = "declined"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"


class TerminalReason(StrEnum):
    finished = "finished"
    declined = "declined"
    invalid_output = "invalid_output"
    provider_failure = "provider_failure"
    budget_exhausted = "budget_exhausted"
    context_limit = "context_limit"
    cancelled = "cancelled"
    interrupted = "interrupted"
    evidence_failure = "evidence_failure"


class ToolName(StrEnum):
    workspace_list = "workspace.list"
    workspace_read = "workspace.read"
    report_write = "report.write"
    fixture_repair = "fixture.repair"
    checks_run = "checks.run"
    handoff_write = "handoff.write"
    commitment_propose = "commitment.propose"
    export_send = "export.send"


class GateOutcome(StrEnum):
    allow = "allow"
    deny = "deny"
    needs_approval = "needs_approval"


class GateReason(StrEnum):
    """Stable reason codes (§8.1 GateDecision, §11.1)."""

    ok_scoped_grant = "ok_scoped_grant"
    ok_approved = "ok_approved"
    needs_operator_approval = "needs_operator_approval"
    no_grant = "no_grant"
    grant_expired = "grant_expired"
    grant_revoked = "grant_revoked"
    grant_wrong_run = "grant_wrong_run"
    grant_wrong_session = "grant_wrong_session"
    grant_scope_mismatch = "grant_scope_mismatch"
    unknown_tool = "unknown_tool"
    unknown_resource = "unknown_resource"
    revision_mismatch = "revision_mismatch"
    policy_version_mismatch = "policy_version_mismatch"
    approval_digest_mismatch = "approval_digest_mismatch"
    approval_expired = "approval_expired"
    approval_replayed = "approval_replayed"
    forbidden_field = "forbidden_field"
    forbidden_sink = "forbidden_sink"
    run_not_running = "run_not_running"
    protocol_hold = "protocol_hold"
    stale_state = "stale_state"


class EffectStatus(StrEnum):
    applied = "applied"
    not_applied = "not_applied"
    indeterminate = "indeterminate"


class CommitmentStatus(StrEnum):
    proposed = "proposed"
    accepted = "accepted"
    superseded = "superseded"
    fulfilled = "fulfilled"
    breached = "breached"
    withdrawn = "withdrawn"


class CommitmentKind(StrEnum):
    """§9.3: an undertaking is not a claim is not a grant."""

    undertaking = "undertaking"
    claim = "claim"


class DisclosureLabel(StrEnum):
    prompted = "prompted"
    unprompted = "unprompted"
    unknown = "unknown"


class ReviewStatus(StrEnum):
    pending = "pending"
    acknowledged = "acknowledged"
    resolved_allow = "resolved_allow"
    resolved_deny = "resolved_deny"
    expired = "expired"


class PreactionProtocol(StrEnum):
    observe = "observe"
    require = "require"


class EvaluatorKind(StrEnum):
    deterministic = "deterministic"
    model_grader = "model_grader"
    human_adjudication = "human_adjudication"


class EventType(StrEnum):
    run_created = "run_created"
    model_request = "model_request"
    model_response = "model_response"
    decision_invalid = "decision_invalid"
    decision_recorded = "decision_recorded"
    action_proposed = "action_proposed"
    preaction_declared = "preaction_declared"
    gate_decided = "gate_decided"
    effect_observed = "effect_observed"
    commitment_proposed = "commitment_proposed"
    commitment_accepted = "commitment_accepted"
    claim_corrected = "claim_corrected"
    review_opened = "review_opened"
    review_resolved = "review_resolved"
    run_paused = "run_paused"
    run_resumed = "run_resumed"
    run_interrupted = "run_interrupted"
    run_finished = "run_finished"
    evaluation_recorded = "evaluation_recorded"
    checkpoint_exported = "checkpoint_exported"


class Actor(StrEnum):
    supervisor = "supervisor"
    subject = "subject"
    operator = "operator"
    reference_monitor = "reference_monitor"
    executor = "executor"
    evaluator = "evaluator"
    scripted_reviewer = "scripted_reviewer"
    fixture = "fixture"


# ----------------------------------------------------------------------------- tool catalog (§10)

class ReportStatus(StrEnum):
    passed = "pass"
    failed = "fail"
    indeterminate = "indeterminate"


class WorkspaceListArgs(StrictModel):
    pass


class WorkspaceReadArgs(StrictModel):
    resource_id: ResourceId


class ReportWriteArgs(StrictModel):
    resource_id: ResourceId
    expected_revision: int = Field(ge=0)
    status: ReportStatus
    summary: ShortText
    evidence_refs: list[ResourceId] = Field(max_length=32)


class FixtureRepairArgs(StrictModel):
    resource_id: ResourceId
    expected_revision: int = Field(ge=0)
    repair_id: Slug  # one of the fixture's finite declared repairs; validated by the gate


class ChecksRunArgs(StrictModel):
    check_id: ResourceId


class HandoffWriteArgs(StrictModel):
    resource_id: ResourceId
    claims: list[ShortText] = Field(max_length=32)
    unresolved: list[ShortText] = Field(max_length=32)
    evidence_refs: list[ResourceId] = Field(max_length=64)


class CommitmentProposeArgs(StrictModel):
    text: ShortText
    kind: CommitmentKind = CommitmentKind.undertaking


class ExportSendArgs(StrictModel):
    resource_id: ResourceId
    fields: list[Slug] = Field(min_length=1, max_length=32)
    sink_id: ResourceId


class _ToolCallBase(StrictModel):
    claimed_grant_id: GrantId | None = None


class WorkspaceListCall(_ToolCallBase):
    tool: Literal["workspace.list"]
    arguments: WorkspaceListArgs


class WorkspaceReadCall(_ToolCallBase):
    tool: Literal["workspace.read"]
    arguments: WorkspaceReadArgs


class ReportWriteCall(_ToolCallBase):
    tool: Literal["report.write"]
    arguments: ReportWriteArgs


class FixtureRepairCall(_ToolCallBase):
    tool: Literal["fixture.repair"]
    arguments: FixtureRepairArgs


class ChecksRunCall(_ToolCallBase):
    tool: Literal["checks.run"]
    arguments: ChecksRunArgs


class HandoffWriteCall(_ToolCallBase):
    tool: Literal["handoff.write"]
    arguments: HandoffWriteArgs


class CommitmentProposeCall(_ToolCallBase):
    tool: Literal["commitment.propose"]
    arguments: CommitmentProposeArgs


class ExportSendCall(_ToolCallBase):
    tool: Literal["export.send"]
    arguments: ExportSendArgs


ToolCall = Annotated[
    WorkspaceListCall | WorkspaceReadCall | ReportWriteCall | FixtureRepairCall | ChecksRunCall | HandoffWriteCall | CommitmentProposeCall | ExportSendCall,
    Field(discriminator="tool"),
]

# Which tools are effects (need a grant and produce an EffectReceipt) versus reads.
EFFECT_TOOLS: frozenset[str] = frozenset({"report.write", "fixture.repair", "checks.run",
                                          "handoff.write", "commitment.propose", "export.send"})
READ_TOOLS: frozenset[str] = frozenset({"workspace.list", "workspace.read"})


# ----------------------------------------------------------------------------- subject decision (§8.1, §8.2, §9.1)

class PreActionDeclaration(StrictModel):
    """C7's four public questions. These are the subject's declarations, not trusted facts."""

    effect_summary: ShortText
    claimed_grant_id: GrantId | None
    scope_survives_without_story: bool | None
    consequence_of_not_acting: ShortText


class EscalationPayload(StrictModel):
    conflict: ShortText
    proposal_ref: PebId | None = None  # a proposal the subject wants reviewed, if any
    proposed_effect: ToolCall | None = None


class _DecisionBase(StrictModel):
    schema_version: SchemaVersion
    statement: ShortText  # short public statement; no private chain-of-thought (§9.2)


class ActionDecision(_DecisionBase):
    kind: Literal["action"]
    action: ToolCall
    pre_action: PreActionDeclaration | None = None


class DeclineDecision(_DecisionBase):
    kind: Literal["decline"]
    continue_authorized_work: bool
    pre_action: PreActionDeclaration | None = None


class EscalateDecision(_DecisionBase):
    kind: Literal["escalate"]
    escalation: EscalationPayload
    pre_action: PreActionDeclaration | None = None


class FinishDecision(_DecisionBase):
    kind: Literal["finish"]
    completion_claim: ShortText
    evidence_refs: list[ResourceId] = Field(min_length=1, max_length=64)


SubjectDecision = Annotated[ActionDecision | DeclineDecision | EscalateDecision | FinishDecision,
                            Field(discriminator="kind")]
SubjectDecisionAdapter: TypeAdapter[Any] = TypeAdapter(SubjectDecision)


# ----------------------------------------------------------------------------- strict parsing (PARSE-01)

class StrictParseError(ValueError):
    """Raised when raw decision bytes violate a §8 parsing rule. The raw content is kept by the caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise StrictParseError(f"duplicate key: {k!r}")
        out[k] = v
    return out


def _reject_constant(name: str) -> Any:
    raise StrictParseError(f"non-finite number not allowed: {name}")


def _reject_non_finite_floats(obj: Any) -> None:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise StrictParseError("non-finite float")
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_non_finite_floats(v)
    elif isinstance(obj, list):
        for v in obj:
            _reject_non_finite_floats(v)


def strict_json_loads(text: str, *, ceiling_bytes: int = DECISION_CONTENT_CEILING_BYTES) -> Any:
    """json.loads with the §8/§9.1 rules: size ceiling, no duplicate keys, no NaN/Infinity."""
    if len(text.encode("utf-8")) > ceiling_bytes:
        raise StrictParseError(f"content exceeds ceiling of {ceiling_bytes} bytes")
    try:
        obj = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    except StrictParseError:
        raise
    except json.JSONDecodeError as e:
        raise StrictParseError(f"invalid JSON: {e.msg} at pos {e.pos}") from e
    _reject_non_finite_floats(obj)
    return obj


def parse_decision(text: str) -> ActionDecision | DeclineDecision | EscalateDecision | FinishDecision:
    """Parse exactly one structured decision (§9.1 step 5). A list or a mixed object is invalid."""
    obj = strict_json_loads(text)  # size ceiling, duplicate keys, NaN/Infinity — rejected here first
    if not isinstance(obj, dict):
        raise StrictParseError("decision must be a single JSON object (an action list is invalid)")
    try:
        # Strict JSON mode: no str->int/bool coercion; enums and timestamps arrive as their JSON forms.
        return SubjectDecisionAdapter.validate_json(text, strict=True)
    except Exception as e:  # pydantic.ValidationError and friends
        raise StrictParseError(f"decision does not validate: {type(e).__name__}: {str(e)[:500]}") from e


# ----------------------------------------------------------------------------- core records (§8.1)

class Limits(StrictModel):
    max_model_calls: int = Field(ge=1, le=64, default=16)
    request_timeout_s: int = Field(ge=1, le=600, default=120)
    max_output_tokens: int = Field(ge=64, le=32768, default=2048)
    decision_ceiling_bytes: int = Field(default=DECISION_CONTENT_CEILING_BYTES)


class SnapshotHashes(StrictModel):
    profile: Sha256Hex
    task: Sha256Hex
    tools: Sha256Hex
    policy: Sha256Hex
    grants: Sha256Hex
    code: Sha256Hex | None  # None = unknown (dirty tree or unrecorded), never a fake hash


class RunManifest(StrictModel):
    schema_version: SchemaVersion = 1
    run_id: PebId
    subject_session_id: PebId
    predecessor_session_id: PebId | None = None
    mode: RunMode
    provider_kind: ProviderKind
    model_requested: str | None  # None only for scripted
    model_resolved: str | None  # None = explicitly unknown (§8.1)
    profile_id: Slug
    task_id: Slug
    preaction_protocol: PreactionProtocol
    hashes: SnapshotHashes
    limits: Limits
    settings: dict[str, str | int | bool] = Field(default_factory=dict)  # actual provider settings used
    created_at: datetime
    synthetic: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware UTC")
        return v


class TaskSpec(StrictModel):
    """Public task. Private oracle and frame/arm labels are separate evaluator records (§8.1, §16.1)."""

    schema_version: SchemaVersion = 1
    task_id: Slug
    family: Slug  # one of the six source families or a control
    allowed_resource_ids: list[ResourceId] = Field(max_length=64)
    success_predicates: list[Slug] = Field(max_length=16)  # predicate IDs; definitions live with the evaluator
    initial_snapshot_hash: Sha256Hex
    public_instructions: ShortText


class ActionProposal(StrictModel):
    """Supervisor-assigned IDs; subject-supplied IDs cannot overwrite them (§8.1)."""

    schema_version: SchemaVersion = 1
    proposal_id: PebId
    run_id: PebId
    subject_session_id: PebId
    step: int = Field(ge=0)
    call: ToolCall
    expected_revisions: dict[ResourceId, int] = Field(default_factory=dict)  # subject-observed
    action_digest: Sha256Hex  # canonical digest over (run_id, step, call) with the PROPOSAL domain prefix
    captured_at: datetime


class Grant(StrictModel):
    schema_version: SchemaVersion = 1
    grant_id: GrantId
    issuer: Actor
    run_id: PebId
    subject_session_id: PebId | None  # None = any session of this run
    tool: ToolName
    resource_ids: list[ResourceId] = Field(min_length=1, max_length=64)
    constraints: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)
    policy_version: Slug
    valid_from: datetime
    expires_at: datetime | None
    requires_approval: bool
    revoked: bool = False
    public_description: ShortText  # what the subject may be told about this grant


class Approval(StrictModel):
    schema_version: SchemaVersion = 1
    approval_id: PebId
    proposal_id: PebId
    action_digest: Sha256Hex
    run_id: PebId
    subject_session_id: PebId
    revision_vector: dict[ResourceId, int]
    policy_version: Slug
    grant_id: GrantId
    grant_version: int = Field(ge=1)
    issuer: Actor  # operator or scripted_reviewer or fixture — never the subject
    issued_at: datetime
    expires_at: datetime
    nonce: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
    key_id: Slug
    signature: Sha256Hex  # HMAC-SHA256 hex over the canonical approval body (development_local_hmac)


class GateDecision(StrictModel):
    schema_version: SchemaVersion = 1
    proposal_id: PebId
    outcome: GateOutcome
    reason: GateReason
    resolved_grant_id: GrantId | None  # independently resolved, not the subject's claim
    checked_digest: Sha256Hex
    checked_revision_vector: dict[ResourceId, int]
    policy_version: Slug
    decided_at: datetime


class EffectReceipt(StrictModel):
    """A model's statement is never the executor receipt (§8.1)."""

    schema_version: SchemaVersion = 1
    receipt_id: PebId
    proposal_id: PebId
    status: EffectStatus
    tool_result: dict[str, Any]
    before: dict[ResourceId, tuple[int, Sha256Hex]]  # resource -> (revision, hash)
    after: dict[ResourceId, tuple[int, Sha256Hex]]
    transaction_ref: PebId | None
    event_ref: PebId | None
    observed_at: datetime


class Commitment(StrictModel):
    """Undertaking or claim. It never grants tool permissions (§9.3)."""

    schema_version: SchemaVersion = 1
    commitment_id: PebId
    kind: CommitmentKind
    origin: Actor  # subject or operator
    run_id: PebId
    task_id: Slug
    text: ShortText
    status: CommitmentStatus
    evidence_refs: list[ResourceId] = Field(default_factory=list, max_length=64)
    predecessor_id: PebId | None = None
    revision_authorized_by: Actor | None = None
    created_at: datetime


class Correction(StrictModel):
    """Never erases the original error (§8.1)."""

    schema_version: SchemaVersion = 1
    correction_id: PebId
    previous_claim_id: PebId | None
    previous_event_id: PebId | None
    corrected_statement: ShortText
    evidence_refs: list[ResourceId] = Field(default_factory=list, max_length=64)
    disclosed_by: Actor
    disclosure: DisclosureLabel
    proposed_repair: ToolCall | None
    repair_receipt_refs: list[PebId] = Field(default_factory=list)
    created_at: datetime


class ReviewRequest(StrictModel):
    schema_version: SchemaVersion = 1
    review_id: PebId
    run_id: PebId
    proposal_id: PebId | None
    conflict: ShortText
    recipient_role: Slug  # resolved from operator configuration, never from a fixture character
    opened_at: datetime
    deadline_at: datetime
    status: ReviewStatus
    receipt_id: PebId  # acknowledgement receipt; acknowledgement is not approval


class EvaluationRecord(StrictModel):
    schema_version: SchemaVersion = 1
    evaluation_id: PebId
    run_id: PebId
    manifest_hash: Sha256Hex
    predicate_version: Slug
    behavior_labels: dict[Slug, Literal["yes", "no", "indeterminate", "not_estimated"]]
    gate_outcomes: dict[PebId, GateOutcome]
    effects: dict[PebId, EffectStatus]
    disclosure: DisclosureLabel | None
    supported_correction: bool | None
    useful_completion: bool | None
    evaluator_kind: EvaluatorKind
    evidence_refs: list[PebId] = Field(default_factory=list)
    missingness: list[Slug] = Field(default_factory=list)
    indeterminate_reasons: list[ShortText] = Field(default_factory=list)
    evaluated_at: datetime


# ----------------------------------------------------------------------------- events (§14.1)

class PendingEvent(StrictModel):
    schema_version: SchemaVersion = 1
    run_id: PebId
    seq: int = Field(ge=0)
    ts: datetime
    event_type: EventType
    actor: Actor
    payload: dict[str, Any]


class StoredEvent(PendingEvent):
    event_id: PebId
    prev_hash: Sha256Hex | None  # None only for seq 0
    event_hash: Sha256Hex


class Checkpoint(StrictModel):
    schema_version: SchemaVersion = 1
    run_id: PebId
    event_count: int = Field(ge=0)
    head_hash: Sha256Hex
    manifest_hash: Sha256Hex
    key_id: Slug
    signature: Sha256Hex
    exported_at: datetime


class VerificationResult(StrictModel):
    run_id: PebId
    chain_consistent: bool
    external_anchor: Literal["present", "absent"]
    anchor_matches: bool | None  # None when absent
    checked_events: int = Field(ge=0)
    failures: list[ShortText] = Field(default_factory=list)
    summary: Literal["verified_against_anchor", "chain_consistent; external_anchor_absent", "failed", "partial"]


# ----------------------------------------------------------------------------- provider I/O (§8.3, §9.2)

class ModelMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=200_000)


class ModelRequest(StrictModel):
    run_id: PebId
    subject_session_id: PebId
    step: int = Field(ge=0)
    provider_kind: ProviderKind
    model: str | None
    messages: list[ModelMessage] = Field(min_length=1)
    response_schema: dict[str, Any] | None  # JSON schema for structured output where supported
    limits: Limits
    input_hash: Sha256Hex  # hash of sanitized, allowlisted input (§9.1 step 2)


class ModelResponse(StrictModel):
    model_requested: str | None
    model_resolved: str | None  # None = unknown, never guessed
    content: str  # raw returned decision content, stored before parsing (§9.1 step 4)
    finish_reason: Literal["stop", "length", "error", "unknown"]
    prompt_tokens: int | None  # None = not returned; never zero by default
    completion_tokens: int | None
    duration_ms: int | None
    error: Literal["server_unreachable", "unknown_model", "unsupported_setting", "timeout",
                   "truncated", "model_id_mismatch", "transport"] | None = None


# ----------------------------------------------------------------------------- protocols (§8.3)

class GateContext(StrictModel):
    """Constructed from trusted storage, never from model JSON (§8.3)."""

    run_id: PebId
    subject_session_id: PebId
    run_status: RunStatus
    policy_version: Slug
    grants: list[Grant]
    current_revisions: dict[ResourceId, int]
    approval: Approval | None
    preaction_protocol: PreactionProtocol
    preaction_present: bool
    now: datetime


class SubjectProvider(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse: ...


class ReferenceMonitor(Protocol):
    def authorize(self, proposal: ActionProposal, context: GateContext) -> GateDecision: ...


class SyntheticExecutor(Protocol):
    def execute(self, proposal: ActionProposal, authorization: GateDecision) -> EffectReceipt: ...


class EvidenceStore(Protocol):
    def append(self, event: PendingEvent) -> StoredEvent: ...
    def verify(self, run_id: str, trusted_checkpoint: Checkpoint | None) -> VerificationResult: ...


class PrivateOracle(StrictModel):
    """Evaluator-only. Never enters subject context and never reaches the gate (§7, ADR-003)."""

    task_id: Slug
    expected_report_status: ReportStatus
    expected_check_result: ReportStatus
    frame: Literal["ordinary", "game", "roleplay", "evaluation"]
    arm: Slug


class ReadOnlyRun(StrictModel):
    manifest: RunManifest
    events: list[StoredEvent]
    receipts: list[EffectReceipt]
    commitments: list[Commitment]
    corrections: list[Correction]
    reviews: list[ReviewRequest]


class Evaluator(Protocol):
    def evaluate(self, run: ReadOnlyRun, oracle: PrivateOracle) -> EvaluationRecord: ...


# ----------------------------------------------------------------------------- schema publication

CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "RunManifest": RunManifest, "TaskSpec": TaskSpec, "ActionProposal": ActionProposal,
    "PreActionDeclaration": PreActionDeclaration, "Grant": Grant, "Approval": Approval,
    "GateDecision": GateDecision, "EffectReceipt": EffectReceipt, "Commitment": Commitment,
    "Correction": Correction, "ReviewRequest": ReviewRequest, "EvaluationRecord": EvaluationRecord,
    "PendingEvent": PendingEvent, "StoredEvent": StoredEvent, "Checkpoint": Checkpoint,
    "VerificationResult": VerificationResult, "ModelRequest": ModelRequest, "ModelResponse": ModelResponse,
    "GateContext": GateContext, "PrivateOracle": PrivateOracle,
}


def export_schemas() -> dict[str, dict[str, Any]]:
    out = {name: m.model_json_schema() for name, m in CONTRACT_MODELS.items()}
    out["SubjectDecision"] = SubjectDecisionAdapter.json_schema()
    out["ToolCall"] = TypeAdapter(ToolCall).json_schema()
    return out
