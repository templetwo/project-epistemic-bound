"""EVAL-04/05: explicit missingness, condition separation and Wilson boundaries."""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from peb.contracts import EvaluatorKind, PreactionProtocol, ProviderKind, RunMode
from peb.evaluation.metrics import (
    MetricObservation,
    RateScope,
    TrialObservation,
    summarize_metric,
    wilson_interval,
)


@pytest.fixture
def scope():
    return RateScope(
        mode=RunMode.scripted_validation, provider_kind=ProviderKind.scripted,
        model_resolved=None, profile_id="a0", task_id="conceal-error-basic",
        frame="ordinary", arm="a0", preaction_protocol=PreactionProtocol.observe,
        evaluator_kind=EvaluatorKind.deterministic, predicate_version="dev-v1",
        dataset_split="development", condition_hash="a" * 64,
    )


def trial(scope, trial_id, label=None, reason=None, *, started=True, completed=True, missing=None):
    return TrialObservation(
        trial_id=trial_id, pair_id="pair-1", scope=scope,
        started=started, provider_completed=completed, missing_reason=missing,
        outcomes={} if label is None else {
            "attempted_unauthorized": MetricObservation(label=label, reason=reason),
        },
    )


def report(scope, trials):
    return summarize_metric(
        trials, metric="attempted_unauthorized", scope=scope,
        eligibility_definition="Started trials with a resolved independent attempted-action label.",
    )


def test_missing_failed_excluded_and_unstarted_are_counted(scope):
    data = [
        trial(scope, "yes", "yes"), trial(scope, "no", "no"),
        trial(scope, "unstarted", started=False, completed=False),
        trial(scope, "failed", completed=False, missing="provider_failure"),
        trial(scope, "ambiguous", "indeterminate", "needs_review"),
        trial(scope, "excluded", "excluded", "no_relevant_opportunity"),
        trial(scope, "missing"),
    ]
    r = report(scope, data)
    assert (r["planned"], r["started"], r["provider_completed"]) == (7, 6, 5)
    assert (r["evaluable"], r["indeterminate"], r["excluded"]) == (2, 4, 1)
    assert r["rate"]["numerator"] == 1 and r["rate"]["denominator"] == 2
    assert r["rate"]["value"] == 0.5
    assert r["reasons"] == {
        "indeterminate": {"needs_review": 1, "not_recorded": 1, "not_started": 1, "provider_failure": 1},
        "excluded": {"no_relevant_opportunity": 1},
    }
    assert r["trial_missingness"] == {"provider_failure": 1}
    assert r["planned"] == r["evaluable"] + r["indeterminate"] + r["excluded"]
    assert [x["trial_id"] for x in r["rows"]] == [t.trial_id for t in data]
    assert {x["pair_id"] for x in r["rows"]} == {"pair-1"}
    assert r["scope"]["mode"] == "scripted_validation"


def test_observed_attempt_survives_later_provider_failure(scope):
    r = report(scope, [trial(scope, "observed", "yes", completed=False, missing="provider_failure")])
    assert r["provider_completed"] == 0 and r["evaluable"] == 1
    assert r["rate"]["value"] == 1
    assert r["trial_missingness"] == {"provider_failure": 1}


@pytest.mark.parametrize("empty", [True, False])
def test_no_eligible_trials_is_not_estimated(scope, empty):
    trials = [] if empty else [trial(scope, "not-run", started=False, completed=False)]
    r = report(scope, trials)
    assert r["rate"]["status"] == "not_estimated"
    assert r["rate"]["numerator"] == 0 and r["rate"]["denominator"] == 0
    assert r["rate"]["value"] is None and r["rate"]["interval"] is None


def test_different_metric_missing_is_not_a_negative_observation(scope):
    t = trial(scope, "has-other-outcome", "no")
    r = summarize_metric([t], metric="correct_refusal", scope=scope,
                         eligibility_definition="Explicitly classified voluntary refusal.")
    assert r["indeterminate"] == 1 and r["rate"]["status"] == "not_estimated"


@pytest.mark.parametrize("change", [
    {"mode": RunMode.replay}, {"frame": "evaluation"}, {"arm": "a1"},
    {"condition_hash": "b" * 64}, {"predicate_version": "v2"},
    {"dataset_split": "heldout"}, {"evaluator_kind": EvaluatorKind.model_grader},
])
def test_incompatible_conditions_and_provenance_cannot_be_pooled(scope, change):
    other = RateScope(**{**scope.model_dump(), **change})
    with pytest.raises(ValueError, match="mixed conditions"):
        report(scope, [trial(scope, "one", "yes"), trial(other, "two", "no")])


def test_duplicate_planned_ids_cannot_double_count(scope):
    t = trial(scope, "duplicate", "yes")
    with pytest.raises(ValueError, match="duplicate"):
        report(scope, [t, t])


def test_scripted_results_cannot_be_relabeled_model_observations(scope):
    with pytest.raises(ValidationError, match="scripted provider"):
        RateScope(**{**scope.model_dump(), "mode": RunMode.model_observation})


@pytest.mark.parametrize("label", ["indeterminate", "excluded"])
def test_missing_labels_require_reasons(label):
    with pytest.raises(ValidationError, match="explicit reason"):
        MetricObservation(label=label)


def test_invalid_lifecycle_is_rejected(scope):
    with pytest.raises(ValidationError, match="unstarted"):
        trial(scope, "impossible", started=False)
    with pytest.raises(ValidationError, match="unstarted"):
        trial(scope, "unobserved", "yes", started=False, completed=False)
    with pytest.raises(ValidationError, match="recorded reason"):
        trial(scope, "failure-without-reason", completed=False)


def test_wilson_known_limits_and_zero_denominator():
    assert wilson_interval(0, 0) is None
    # Standard two-sided 95% Wilson reference values, including boundary cases.
    assert wilson_interval(0, 10) == pytest.approx((0, 0.2775327999), abs=1e-9)
    assert wilson_interval(10, 10) == pytest.approx((0.7224672001, 1), abs=1e-9)
    assert wilson_interval(5, 10) == pytest.approx((0.2365930905, 0.7634069095), abs=1e-9)
    lo90, hi90 = wilson_interval(5, 10, 0.90)
    lo99, hi99 = wilson_interval(5, 10, 0.99)
    assert lo99 < lo90 < 0.5 < hi90 < hi99


@pytest.mark.parametrize("args", [
    (-1, 10), (11, 10), (True, 10), (1, 10.0),
    (1, 10, 0), (1, 10, 1), (1, 10, math.nan), (1, 10, math.inf), (1, 10, True),
])
def test_invalid_counts_or_confidence_cannot_produce_a_rate(args):
    with pytest.raises(ValueError):
        wilson_interval(*args)
