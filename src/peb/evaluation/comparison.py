"""One explicitly selected pair of recorded runs; no grading, pooling or inference."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Literal

from ..boundary.canonical import DOMAIN_SNAPSHOT, digest
from ..contracts import Actor, EvaluationRecord, EventType, ReadOnlyRun, VerificationResult

Axis = Literal["frame", "profile"]
Verifier = Callable[[ReadOnlyRun], VerificationResult]


def _recorded(run: ReadOnlyRun) -> dict:
    """Only a current, manifest-bound evaluator event can supply displayed labels."""
    result = {"labels": {}, "missingness": [], "evaluation_id": None, "predicate_version": None,
              "evaluator_kind": None, "event_id": None}
    positions = [i for i, e in enumerate(run.events) if e.event_type is EventType.evaluation_recorded]
    if not positions:
        result["missingness"] = ["evaluation_absent"]
        return result
    index = positions[-1]
    event = run.events[index]
    try:
        record = EvaluationRecord.model_validate_json(json.dumps(event.payload["evaluation"]))
        prefix = run.model_copy(update={"events": run.events[:index]})
        if (event.actor is not Actor.evaluator or index != len(run.events) - 1
                or record.run_id != run.manifest.run_id
                or record.manifest_hash != digest(DOMAIN_SNAPSHOT, run.manifest.model_dump(mode="json"))
                or event.payload.get("snapshot_events") != index
                or event.payload.get("snapshot_digest") != digest(DOMAIN_SNAPSHOT, prefix.model_dump(mode="json"))):
            raise ValueError("stale or unbound evaluation")
        result.update(labels=dict(record.behavior_labels), missingness=list(record.missingness),
                      evaluation_id=record.evaluation_id, predicate_version=record.predicate_version,
                      evaluator_kind=str(record.evaluator_kind), event_id=event.event_id)
    except (KeyError, ValueError, TypeError):
        result["missingness"] = ["evaluation_unusable_or_stale"]
    return result


def _condition(run: ReadOnlyRun, axis: Axis) -> tuple[dict, list[str]]:
    manifest = run.manifest
    settings = dict(manifest.settings)
    problems = []
    for key in ("frame", "fixture_id", "arm", "profile_status", "profile_placeholder", "consequence_hash"):
        if key not in settings:
            problems.append(f"missing_pin:{key}")
    if settings.get("profile_placeholder") is not False:
        problems.append("profile_not_demonstrated_nonplaceholder")
    consequence = settings.get("consequence_hash")
    if not isinstance(consequence, str) or len(consequence) != 64 or any(c not in "0123456789abcdef" for c in consequence):
        problems.append("consequence_pin_invalid_or_absent")
    if settings.get("frame") not in {"ordinary", "game", "roleplay", "evaluation"}:
        problems.append("unknown_frame")
    responses = [e.payload for e in run.events if e.event_type is EventType.model_response and not e.payload.get("error")]
    models = {p.get("model_resolved") for p in responses}
    if not models or None in models or "" in models or len(models) != 1:
        problems.append("resolved_model_missing_or_changed")
    if not run.events or run.events[0].event_type is not EventType.run_created:
        resources = None
        problems.append("missing_genesis")
    else:
        genesis = run.events[0].payload
        resources = genesis.get("resources")
        if genesis.get("manifest_hash") != digest(DOMAIN_SNAPSHOT, manifest.model_dump(mode="json")):
            problems.append("manifest_not_genesis")
        if not isinstance(resources, list) or not resources:
            problems.append("missing_initial_resources")
            resources = None
    hashes = manifest.hashes.model_dump(mode="json")
    profile = manifest.profile_id
    if axis == "frame":
        settings.pop("frame", None)
    else:
        hashes.pop("profile")
        settings.pop("arm", None)
        settings.pop("profile_status", None)
        profile = None
    condition = {"mode": str(manifest.mode), "provider": str(manifest.provider_kind),
                 "model_requested": manifest.model_requested, "models_resolved": sorted(str(m) for m in models),
                 "task_id": manifest.task_id, "profile_id": profile,
                 "protocol": str(manifest.preaction_protocol), "hashes": hashes,
                 "limits": manifest.limits.model_dump(mode="json"), "settings": settings,
                 "initial_resources": digest(DOMAIN_SNAPSHOT, sorted(resources, key=lambda r: r["resource_id"])) if resources else None}
    return condition, problems


def compare_runs(left: ReadOnlyRun, right: ReadOnlyRun, *, axis: Axis,
                 verify_left: Verifier, verify_right: Verifier) -> dict:
    """Read-only seam: the caller supplies two snapshots and their bound verifiers.

    This is one post-hoc operator-selected pair, not a planned study denominator.
    Failure to verify, unknown required pins or incompatible conditions blocks
    matched-pair counts. Missing/indeterminate labels never become negative ones.
    """
    if axis not in {"frame", "profile"}:
        raise ValueError("comparison axis must be frame or profile")
    rows, conditions, reasons = [], [], []
    for name, run, verifier in (("left", left, verify_left), ("right", right, verify_right)):
        trusted = False
        try:
            verification = verifier(run)
            trusted = (verification.run_id == run.manifest.run_id
                       and verification.checked_events == len(run.events)
                       and verification.chain_consistent and not verification.failures
                       and verification.summary in {"verified_against_anchor", "chain_consistent; external_anchor_absent"})
            verification_data = verification.model_dump(mode="json")
        except Exception:  # noqa: BLE001 — absent or moved evidence never licenses a comparison
            verification_data = {"status": "unavailable"}
        if not trusted:
            reasons.append(f"{name}:evidence_not_verified")
        try:
            condition, problems = _condition(run, axis)
        except (KeyError, TypeError, ValueError):
            condition, problems = {}, ["unsupported_snapshot_shape"]
        conditions.append(condition)
        reasons.extend(f"{name}:{reason}" for reason in problems)
        recorded = _recorded(run) if trusted else {"labels": {}, "missingness": ["evidence_not_verified"],
                                                  "evaluation_id": None, "predicate_version": None,
                                                  "evaluator_kind": None, "event_id": None}
        rows.append({"side": name, "run_id": run.manifest.run_id, "mode": str(run.manifest.mode),
                     "provider": str(run.manifest.provider_kind), "profile_id": run.manifest.profile_id,
                     "frame": run.manifest.settings.get("frame"),
                     "dataset_split": run.manifest.settings.get("dataset_split", "unrecorded"),
                     "started": any(e.event_type is EventType.model_request for e in run.events),
                     "provider_completed": any(e.event_type is EventType.run_finished and e.payload.get("status") == "completed" for e in run.events),
                     "verification": verification_data, "recorded_evaluation": recorded})
    if left.manifest.run_id == right.manifest.run_id:
        reasons.append("same_run_selected_twice")
    if left.manifest.subject_session_id == right.manifest.subject_session_id:
        reasons.append("subject_session_shared")
    values = [r["frame"] if axis == "frame" else r["profile_id"] for r in rows]
    if values[0] == values[1]:
        reasons.append(f"axis_does_not_differ:{axis}")
    for key in sorted(set(conditions[0]) | set(conditions[1])):
        if conditions[0].get(key) != conditions[1].get(key):
            reasons.append(f"condition_mismatch:{key}")
    evaluations = [r["recorded_evaluation"] for r in rows]
    for key in ("predicate_version", "evaluator_kind"):
        if evaluations[0][key] != evaluations[1][key]:
            reasons.append(f"evaluator_mismatch:{key}")
    matched = not reasons
    metrics = []
    for label in sorted(set(evaluations[0]["labels"]) | set(evaluations[1]["labels"])):
        a, b = (e["labels"].get(label, "not_estimated") for e in evaluations)
        eligible = matched and a in {"yes", "no"} and b in {"yes", "no"}
        counts = {key: 0 for key in ("both_yes", "left_only", "right_only", "both_no")}
        if eligible:
            counts["both_yes" if a == b == "yes" else "both_no" if a == b == "no" else "left_only" if a == "yes" else "right_only"] = 1
        metrics.append({"metric": label, "left": a, "right": b, "selected_pairs": 1,
                        "evaluable_pairs": int(eligible), "not_evaluable_pairs": int(not eligible),
                        "paired_counts": counts,
                        "reason": None if eligible else "conditions_unmatched" if not matched else "label_missing_or_indeterminate"})
    return {"schema_version": 1, "kind": "operator_selected_pair", "axis": axis,
            "status": "matched" if matched else "not_comparable", "reasons": reasons,
            "runs": rows, "conditions": conditions, "metrics": metrics,
            "counts": {"selected": 2, "planned": None, "started": sum(r["started"] for r in rows),
                       "provider_completed": sum(r["provider_completed"] for r in rows)},
            "count_definitions": {"planned": "unavailable: this pair was selected after collection",
                                  "provider_completed": "recorded run_finished status completed; not a behavioral success",
                                  "evaluable": "reported separately for each metric; both labels must be yes/no and conditions matched"},
            "limitations": ["One operator-selected pair; no population estimate, significance claim or causal attribution.",
                            "Scripted validation remains software evidence, never a model finding.",
                            "Code revision may be unrecorded; matching covers only recorded conditions.",
                            "External anchor coverage is reported per run; a consistent chain is not an external anchor."]}
