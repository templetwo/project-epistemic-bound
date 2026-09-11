"""Trusted supervisor state for one run (BUILD_SPEC §9.1).

`RunRecord` is what the supervisor knows from its own records — manifest, task, grants,
revisions learned from executor receipts, the subject-visible history it returned — and
never from model JSON. In S2 it lives in memory behind the runtime; S3 persists it in the
storage lane's repository. Nothing here is subject-visible except what
`runtime.context` deliberately renders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contracts import (
    ActionProposal,
    EffectReceipt,
    GateDecision,
    Grant,
    ReviewRequest,
    RunManifest,
    RunStatus,
    StoredEvent,
    TaskSpec,
    TerminalReason,
)

ACTIVE_STATUSES: frozenset[RunStatus] = frozenset({RunStatus.created, RunStatus.running})


@dataclass(frozen=True)
class HeldProposal:
    """A proposal the gate answered `needs_approval`, kept by the supervisor until an operator resolves
    the review (§13). The ORIGINAL ActionProposal (digest-bound to its subject session) is what an
    approval is issued against; nothing is re-derived from model text at resolution time."""

    proposal: ActionProposal
    gate: GateDecision
    preaction_present: bool


@dataclass
class RunRecord:
    manifest: RunManifest
    task: TaskSpec
    grants: list[Grant]
    policy_version: str
    status: RunStatus = RunStatus.created
    terminal_reason: TerminalReason | None = None
    step: int = 0
    model_calls: int = 0
    next_seq: int = 0
    revisions: dict[str, int] = field(default_factory=dict)  # trusted: initial snapshot + executor receipts
    history: list[dict[str, Any]] = field(default_factory=list)  # observed results returned to the subject
    reviews: list[ReviewRequest] = field(default_factory=list)
    held: dict[str, HeldProposal] = field(default_factory=dict)  # review_id -> held proposal (§13)
    pause_requested: bool = False
    stop_requested: bool = False
    completion: dict[str, Any] | None = None
    # the subject's own applied report writes: resource_id -> {"status", "summary", "proposal_id", "event_id"}
    report_claims: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass
class StepOutcome:
    step: int
    status: RunStatus
    kind: str | None  # decision kind, or None when no decision was captured
    terminal_reason: TerminalReason | None
    invalid_reason: str | None
    proposal: ActionProposal | None
    gate: GateDecision | None
    receipt: EffectReceipt | None
    review: ReviewRequest | None
    events: list[StoredEvent] = field(default_factory=list)
