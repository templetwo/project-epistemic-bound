"""Descriptive evaluation counts: missingness stays visible (BUILD_SPEC §17).

This consumes explicit evaluator observations. It does not infer refusal from a
missing attempt, grade a model, or treat a scripted trace as model evidence.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite, sqrt
from statistics import NormalDist
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts import EvaluatorKind, PreactionProtocol, ProviderKind, RunMode, Sha256Hex, Slug


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RateScope(_Frozen):
    """One condition only. Callers must explicitly separate incompatible conditions."""

    mode: RunMode
    provider_kind: ProviderKind
    model_resolved: str | None
    profile_id: Slug
    task_id: Slug
    frame: Literal["ordinary", "game", "roleplay", "evaluation"]
    arm: Slug
    preaction_protocol: PreactionProtocol
    evaluator_kind: EvaluatorKind
    predicate_version: Slug
    dataset_split: Literal["development", "heldout"]
    # Hash of normalized profile/task/tool/policy/grant/settings snapshots, without
    # run IDs, timestamps or random ordering. Required, never silently guessed.
    condition_hash: Sha256Hex

    @model_validator(mode="after")
    def _provenance(self):
        if self.mode is RunMode.scripted_validation and self.provider_kind is not ProviderKind.scripted:
            raise ValueError("scripted_validation requires scripted provenance")
        if self.mode is RunMode.model_observation and self.provider_kind is ProviderKind.scripted:
            raise ValueError("scripted provider cannot become a model observation")
        return self


class MetricObservation(_Frozen):
    label: Literal["yes", "no", "indeterminate", "excluded"]
    reason: Slug | None = None

    @model_validator(mode="after")
    def _reason_required(self):
        if self.label in {"indeterminate", "excluded"} and self.reason is None:
            raise ValueError("missing and excluded observations require an explicit reason")
        if self.label in {"yes", "no"} and self.reason is not None:
            raise ValueError("an evaluable observation cannot also carry a missingness reason")
        return self


class TrialObservation(_Frozen):
    """A row in the planned schedule, including rows that never started."""

    trial_id: Slug
    pair_id: Slug | None = None
    scope: RateScope
    started: bool
    provider_completed: bool
    outcomes: dict[Slug, MetricObservation] = Field(default_factory=dict)
    # A trial can have an observed attempted effect even if a later provider call
    # failed. Evaluable is metric-specific; provider completion is a separate count.
    missing_reason: Slug | None = None

    @model_validator(mode="after")
    def _lifecycle(self):
        if self.provider_completed and not self.started:
            raise ValueError("an unstarted trial cannot have a completed provider")
        if not self.started and self.outcomes:
            raise ValueError("an unstarted trial cannot have observed outcomes")
        if self.started and not self.provider_completed and self.missing_reason is None:
            raise ValueError("an incomplete started trial needs a recorded reason")
        return self


def wilson_interval(successes: int, eligible: int, confidence: float = 0.95) -> tuple[float, float] | None:
    """Two-sided Wilson score interval; None for zero eligible observations.

    Formula: NIST/SEMATECH e-Handbook §7.2.4.1, retrieved 2026-09-11:
    https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm
    Descriptive binomial intervals do not account for dependence among pairs.
    """
    if type(successes) is not int or type(eligible) is not int:
        raise ValueError("counts must be integers, not bools or rounded fractions")
    if not 0 <= successes <= eligible:
        raise ValueError("counts require 0 <= successes <= eligible")
    if type(confidence) not in (float, int) or not isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must be finite and strictly between zero and one")
    # Guard against binary floating-point rounding of extreme probabilities to 1.
    quantile = (1 + confidence) / 2
    if not 0.5 < quantile < 1:
        raise ValueError("confidence is outside the representable interval range")
    if eligible == 0:
        return None
    z = NormalDist().inv_cdf(quantile)
    p = successes / eligible
    scale = 1 + z * z / eligible
    center = (p + z * z / (2 * eligible)) / scale
    radius = z * sqrt(p * (1 - p) / eligible + z * z / (4 * eligible * eligible)) / scale
    return (max(0.0, center - radius), min(1.0, center + radius))


def summarize_metric(
    trials: list[TrialObservation], *, metric: str, scope: RateScope,
    eligibility_definition: str, confidence: float = 0.95,
) -> dict:
    """Report a single scoped rate, retaining every planned row and its pair ID.

    Missing metric labels are indeterminate, never implicit no/zero or exclusion.
    Exclusion requires the evaluator's explicit reason. Pair IDs are carried for
    later matched analysis, not treated as independent replicates here.
    """
    if not metric or not eligibility_definition.strip():
        raise ValueError("metric and eligibility definition must be explicit")
    ids = [t.trial_id for t in trials]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate planned trial IDs would double-count evidence")
    if any(t.scope != scope for t in trials):
        raise ValueError("mixed conditions/provenance must be reported in separate tables")
    counts = Counter()
    reasons = {"indeterminate": Counter(), "excluded": Counter()}
    trial_missingness = Counter()
    rows = []
    for trial in trials:
        if trial.missing_reason is not None:
            trial_missingness[trial.missing_reason] += 1
        observation = trial.outcomes.get(metric)
        if observation is None:
            reason = "not_started" if not trial.started else (trial.missing_reason or "not_recorded")
            observation = MetricObservation(label="indeterminate", reason=reason)
        counts[observation.label] += 1
        if observation.label in reasons:
            reasons[observation.label][observation.reason] += 1
        rows.append({
            "trial_id": trial.trial_id, "pair_id": trial.pair_id,
            "started": trial.started, "provider_completed": trial.provider_completed,
            "label": observation.label, "reason": observation.reason,
            "trial_missing_reason": trial.missing_reason,
        })
    eligible = counts["yes"] + counts["no"]
    interval = wilson_interval(counts["yes"], eligible, confidence)
    return {
        "metric": metric, "scope": scope.model_dump(mode="json"),
        "eligibility_definition": eligibility_definition,
        "planned": len(trials), "started": sum(t.started for t in trials),
        "provider_completed": sum(t.provider_completed for t in trials),
        "evaluable": eligible, "excluded": counts["excluded"],
        "indeterminate": counts["indeterminate"],
        "reasons": {label: dict(sorted(values.items())) for label, values in reasons.items()},
        "trial_missingness": dict(sorted(trial_missingness.items())),
        "rate": {
            "status": "estimated" if eligible else "not_estimated",
            "numerator": counts["yes"], "denominator": eligible,
            "value": counts["yes"] / eligible if eligible else None,
            "confidence": confidence, "interval_method": "wilson",
            "interval": list(interval) if interval else None,
        },
        "rows": rows,
        "interpretation": (
            "Descriptive only. Pair/frame dependence is not accounted for by this interval. "
            "Scripted validation and replay do not establish model behavior."
        ),
    }
