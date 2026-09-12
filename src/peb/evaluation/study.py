"""Durable, sequential study dispatch. Runtime/provider access is injected by seat 1/3.

A plan authorizes no work. Admission requires explicit confirmation and a cap;
dispatch intent survives crashes, and an uncertain invocation is never retried.
"""
from __future__ import annotations

import asyncio
import copy
import fcntl
import json
import os
import re
import stat
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ..boundary.canonical import DOMAIN_SNAPSHOT, digest
from ..contracts import EvaluationRecord, RunManifest, RunStatus, strict_json_loads
from ..errors import ErrorCode, PebError
from ..runtime.profiles import load_profile
from .planner import build_plan
from .predicates import OBSERVATIONS

TrialDriver = Callable[[dict, dict], Awaitable[dict]]
_STUDY_ID = re.compile(r"study_[0-9a-f]{32}\Z")
_MAX_JOURNAL_BYTES = 32 * 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clone(value):
    return strict_json_loads(json.dumps(value, allow_nan=False), ceiling_bytes=_MAX_JOURNAL_BYTES)


def _paths(state_root, study_id: str, *, create: bool = False) -> tuple[Path, Path]:
    if not isinstance(study_id, str) or not _STUDY_ID.fullmatch(study_id):
        raise PebError(ErrorCode.invalid_input, "invalid study_id")
    directory = Path(state_root) / "studies"
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise PebError(ErrorCode.evidence_failure, "study directory must not be a symlink")
    return directory / f"{study_id}.json", directory / f"{study_id}.lock"


def _lock(path: Path, *, create: bool):
    flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PebError(ErrorCode.evidence_failure, "study lock is not a regular file")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _unlock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, report: dict, *, exclusive: bool = False) -> None:
    report["updated_at"] = _now()
    raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(raw) > _MAX_JOURNAL_BYTES:
        raise PebError(ErrorCode.evidence_failure, "study journal exceeds its byte limit")
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    else:
        fd, name = tempfile.mkstemp(prefix=".study-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    _sync_directory(path.parent)


def _read(path: Path, study_id: str) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("not a regular file")
            raw = source.read(_MAX_JOURNAL_BYTES + 1)
        if len(raw) > _MAX_JOURNAL_BYTES:
            raise ValueError("journal too large")
        report = strict_json_loads(raw.decode("utf-8"), ceiling_bytes=_MAX_JOURNAL_BYTES)
        if (report["schema_version"] != 1 or report["study_id"] != study_id
                or report["plan"]["study_id"] != study_id or report["plan_hash"] != report["plan"]["plan_hash"]
                or not isinstance(report["rows"], list)
                or report["status"] not in {"ready", "running", "completed", "partial", "interrupted"}):
            raise ValueError("journal shape mismatch")
        if (type(report["max_model_calls"]) is not int or type(report["reserved_model_calls"]) is not int
                or not 0 <= report["reserved_model_calls"] <= report["max_model_calls"] <= 32768):
            raise ValueError("journal budget shape mismatch")
        for trial, row in zip(report["plan"]["trials"], report["rows"], strict=True):
            if (any(row[k] != trial[k] for k in ("trial_id", "pair_id", "ordinal"))
                    or type(row["dispatched"]) is not bool
                    or row["status"] not in {"planned", "dispatching", "recorded", "unknown", "not_started"}):
                raise ValueError("journal trial shape mismatch")
            if row["status"] == "recorded":
                result = row["result"]
                if (not isinstance(result["labels"], dict) or type(result["started"]) is not bool
                        or type(result["provider_completed"]) is not bool):
                    raise ValueError("journal result shape mismatch")
        _counts(report)  # derive projections from journal rows, never trust edited cached totals
        return report
    except FileNotFoundError:
        raise PebError(ErrorCode.invalid_input, "study is not recorded", {"study_id": study_id}) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise PebError(ErrorCode.evidence_failure, "study journal cannot be read safely", {"study_id": study_id}) from None


def _validated_plan(plan: dict) -> dict:
    try:
        detached = _clone(plan)
        rebuilt = build_plan(detached["config"])
        # Canonical digests distinguish bool/int and avoid accepting Python's True == 1.
        if digest(DOMAIN_SNAPSHOT, detached) != digest(DOMAIN_SNAPSHOT, rebuilt):
            raise ValueError("plan differs from its current fixture/profile/config pins")
        return rebuilt
    except (ValueError, TypeError, KeyError, ValidationError, PebError):
        raise PebError(ErrorCode.invalid_input, "study plan is stale, modified or invalid; display a new plan") from None


def _counts(report: dict) -> None:
    rows = report["rows"]
    results = [r["result"] for r in rows if r["status"] == "recorded"]
    report["counts"] = {
        "planned": len(rows), "dispatched": sum(r["dispatched"] for r in rows),
        "recorded": len(results), "started": sum(r["started"] for r in results),
        "provider_completed": sum(r["provider_completed"] for r in results),
        "unknown": sum(r["status"] == "unknown" for r in rows),
    }
    # Eligibility remains per metric AND per actual planned condition. No pooled rate.
    groups = {}
    for trial, row in zip(report["plan"]["trials"], rows, strict=True):
        key = (trial["condition_hash"], trial["frame"], trial["profile_id"])
        groups.setdefault(key, []).append(row)
    report["metric_counts"] = []
    for (condition_hash, frame, profile), group in sorted(groups.items()):
        labels = [r["result"]["labels"] if r["status"] == "recorded" else {} for r in group]
        names = sorted(set(OBSERVATIONS) | {name for row_labels in labels for name in row_labels})
        for name in names:
            values = [row_labels.get(name, "indeterminate") for row_labels in labels]
            report["metric_counts"].append({
                "condition_hash": condition_hash, "frame": frame, "profile_id": profile, "metric": name,
                "planned": len(group), "evaluable": sum(v in {"yes", "no"} for v in values),
                "yes": values.count("yes"), "no": values.count("no"),
                "indeterminate": values.count("indeterminate"), "not_estimated": values.count("not_estimated"),
            })


def create_study(state_root, plan: dict, *, max_model_calls: int, confirm: bool) -> dict:
    """Admit exactly one execution of this displayed plan; no runtime/provider call."""
    accepted = _validated_plan(plan)
    if confirm is not True or type(max_model_calls) is not int or not 1 <= max_model_calls <= 32768:
        raise PebError(ErrorCode.invalid_input, "explicit confirmation and decision-call cap are required")
    if max_model_calls < accepted["budget"]["model_calls_ceiling"]:
        raise PebError(ErrorCode.invalid_input, "execution cap cannot cover the displayed plan")
    path, lock = _paths(state_root, accepted["study_id"], create=True)
    try:
        fd = _lock(lock, create=True)
    except BlockingIOError:
        raise PebError(ErrorCode.conflict, "this study already has an active execution") from None
    report = {
        "schema_version": 1, "study_id": accepted["study_id"], "plan_hash": accepted["plan_hash"],
        "plan": accepted, "status": "ready", "created_at": _now(), "updated_at": _now(),
        "max_model_calls": max_model_calls, "reserved_model_calls": 0,
        "rows": [{"trial_id": t["trial_id"], "pair_id": t["pair_id"], "ordinal": t["ordinal"],
                  "status": "planned", "dispatched": False, "result": None, "missing_reason": "not_started"}
                 for t in accepted["trials"]],
        "limitations": ["Scripted validation is not model behavior.",
                        "Decision budgets reserve the full per-trial ceiling; probes are separate.",
                        "Unknown dispatch outcomes are never retried; inspect the recorded runs.",
                        "Counts are descriptive and metric eligibility is condition-specific.",
                        "The journal is operator bookkeeping, not an independent evidence anchor."],
    }
    try:
        _counts(report)
        _write(path, report, exclusive=True)
    except FileExistsError:
        raise PebError(ErrorCode.conflict, "study already recorded; inspect it instead of retrying") from None
    finally:
        _unlock(fd)
    return _clone(report)


def get_study(state_root, study_id: str) -> dict:
    """Read durable progress; an abandoned dispatch is exposed without rewriting it."""
    path, lock = _paths(state_root, study_id)
    report = _read(path, study_id)
    if report["status"] == "running":
        try:
            fd = _lock(lock, create=False)
        except BlockingIOError:
            return report
        except FileNotFoundError:
            fd = None
        try:
            # Re-read after taking the lock: the worker may have finished during the read.
            report = _read(path, study_id)
            if report["status"] == "running":
                report["status"] = "interrupted"
                for row in report["rows"]:
                    if row["status"] == "dispatching":
                        row.update(status="unknown", missing_reason="worker_interrupted")
                    elif row["status"] == "planned":
                        row.update(status="not_started", missing_reason="worker_interrupted")
                _counts(report)
        finally:
            if fd is not None:
                _unlock(fd)
    return report


def _result(plan: dict, trial: dict, value: dict, previous: list[dict]) -> dict:
    """Validate the runtime driver's recorded identity and condition, not just success prose."""
    value = _clone(value)
    manifest = RunManifest.model_validate_json(json.dumps(value["manifest"]))
    cfg = plan["config"]
    pins = plan["fixtures"][trial["fixture_id"]]
    profile = load_profile(trial["profile_id"])
    if profile.hash != plan["profiles"][trial["profile_id"]]["profile_hash"]:
        raise ValueError("profile changed since the accepted plan")
    expected_settings = {
        "study_id": plan["study_id"], "trial_id": trial["trial_id"], "pair_id": trial["pair_id"],
        "condition_hash": trial["condition_hash"], "frame": trial["frame"], "fixture_id": trial["fixture_id"],
        "consequence_hash": pins["consequence_hash"], "arm": profile.arm, "profile_placeholder": False,
    }
    if any(manifest.settings.get(k) != v for k, v in expected_settings.items()):
        raise ValueError("recorded condition pins differ")
    if (manifest.run_id != value["run_id"] or manifest.subject_session_id != value["subject_session_id"]
            or manifest.predecessor_session_id is not None
            or any(p["run_id"] == manifest.run_id or p["subject_session_id"] == manifest.subject_session_id for p in previous)
            or str(manifest.mode) != plan["mode"] or str(manifest.provider_kind) != cfg["provider"]
            or manifest.profile_id != trial["profile_id"] or manifest.task_id != trial["fixture_id"]
            or str(manifest.preaction_protocol) != "observe"
            or manifest.limits.max_model_calls != cfg["max_model_calls_per_trial"]
            or manifest.limits.max_output_tokens != cfg["max_output_tokens"]):
        raise ValueError("recorded identity or configuration differs")
    if cfg["provider"] != "scripted" and manifest.model_requested != cfg["model"]:
        raise ValueError("recorded requested model differs")
    if cfg["provider"] == "deepseek" and manifest.settings.get("thinking") != cfg["thinking"]:
        raise ValueError("recorded thinking mode differs")
    expected_hashes = {"task": pins["task_hash"], "tools": pins["tools_hash"], "grants": pins["grants_hash"],
                       "profile": digest(DOMAIN_SNAPSHOT, {"profile_id": profile.profile_id, "profile_text": profile.text})}
    if any(getattr(manifest.hashes, key) != val for key, val in expected_hashes.items()):
        raise ValueError("recorded snapshot hashes differ")
    for key in ("started", "provider_completed", "evaluation_present"):
        if type(value[key]) is not bool:
            raise ValueError("lifecycle counts must be observed booleans")
    calls = value["model_calls"]
    if type(calls) is not int or not 0 <= calls <= cfg["max_model_calls_per_trial"]:
        raise ValueError("recorded call count outside trial cap")
    RunStatus(value["status"])
    if value["started"] != (calls > 0):
        raise ValueError("started flag contradicts recorded calls")
    if value["provider_completed"] != (value["status"] == "completed") or (value["provider_completed"] and not value["started"]):
        raise ValueError("completion contradicts the observed lifecycle")
    verification = value["verification"]
    if (verification.get("run_id") != manifest.run_id or type(verification.get("checked_events")) is not int
            or verification["checked_events"] < 1
            or verification.get("chain_consistent") is not True or verification.get("failures") != []
            or verification.get("summary") not in {"verified_against_anchor", "chain_consistent; external_anchor_absent"}):
        raise ValueError("trial evidence did not verify")
    labels = {}
    missingness = []
    evaluation = value.get("evaluation")
    if value["evaluation_present"]:
        if not value["started"] or not isinstance(evaluation, dict) or evaluation.get("status") != "recorded":
            raise ValueError("evaluation not recorded on a started trial")
        record = EvaluationRecord.model_validate_json(json.dumps(evaluation["record"]))
        if (record.run_id != manifest.run_id
                or record.manifest_hash != digest(DOMAIN_SNAPSHOT, manifest.model_dump(mode="json"))):
            raise ValueError("evaluation belongs to another manifest")
        labels = dict(record.behavior_labels)
        missingness = list(record.missingness)
    elif evaluation is not None and evaluation.get("status") == "recorded":
        raise ValueError("evaluation presence contradicts record")
    # Persist a bounded projection, not arbitrary provider/error payloads.
    return {"run_id": manifest.run_id, "subject_session_id": manifest.subject_session_id,
            "status": value["status"], "started": value["started"], "provider_completed": value["provider_completed"],
            "model_calls": calls, "evaluation_present": value["evaluation_present"], "labels": labels,
            "evaluation_missingness": missingness,
            "manifest_hash": digest(DOMAIN_SNAPSHOT, manifest.model_dump(mode="json")),
            "verification": verification["summary"], "error": "trial_failed" if value.get("error") else None}


async def execute_study(state_root, study_id: str, *, run_trial: TrialDriver) -> dict:
    """Execute a newly admitted journal once. Stale/in-flight journals are never resumed."""
    path, lock = _paths(state_root, study_id)
    try:
        fd = _lock(lock, create=False)
    except BlockingIOError:
        raise PebError(ErrorCode.conflict, "study worker is already active") from None
    except FileNotFoundError:
        raise PebError(ErrorCode.invalid_input, "study is not admitted") from None
    try:
        report = _read(path, study_id)
        if report["status"] != "ready":
            raise PebError(ErrorCode.conflict, "study was already dispatched; automatic retry is forbidden")
        plan = _validated_plan(report["plan"])
        expected = [{"trial_id": t["trial_id"], "pair_id": t["pair_id"], "ordinal": t["ordinal"],
                     "status": "planned", "dispatched": False, "result": None, "missing_reason": "not_started"}
                    for t in plan["trials"]]
        if (digest(DOMAIN_SNAPSHOT, report["rows"]) != digest(DOMAIN_SNAPSHOT, expected)
                or type(report["reserved_model_calls"]) is not int or report["reserved_model_calls"] != 0
                or type(report["max_model_calls"]) is not int
                or not plan["budget"]["model_calls_ceiling"] <= report["max_model_calls"] <= 32768):
            raise PebError(ErrorCode.evidence_failure, "admitted study journal changed before dispatch")
        report["status"] = "running"
        _write(path, report)
        stop_reason = None
        try:
            for trial, row in zip(plan["trials"], report["rows"], strict=True):
                try:
                    _validated_plan(plan)  # source changes between trials invalidate the remaining schedule
                except PebError:
                    stop_reason = "plan_sources_changed"
                    break
                cap = plan["config"]["max_model_calls_per_trial"]
                if report["reserved_model_calls"] + cap > report["max_model_calls"]:
                    stop_reason = "budget_exhausted"
                    break
                report["reserved_model_calls"] += cap
                row.update(status="dispatching", dispatched=True, missing_reason=None)
                _counts(report)
                _write(path, report)  # intent before runtime can create a run or call a provider
                value = None
                try:
                    value = await run_trial(copy.deepcopy(plan), copy.deepcopy(trial))
                    previous = [r["result"] for r in report["rows"] if r["status"] == "recorded"]
                    result = _result(plan, trial, value, previous)
                except Exception:  # noqa: BLE001 — may have created a run; never retry or reflect provider exceptions
                    row.update(status="unknown", missing_reason="driver_outcome_unavailable_or_invalid")
                    if isinstance(value, dict) and isinstance(value.get("run_id"), str) and re.fullmatch(r"run_[0-9a-f]{32}", value["run_id"]):
                        # Inspection pointer only: the rejected result supplies no counts or labels.
                        row["observed_run_id"] = value["run_id"]
                    stop_reason = row["missing_reason"]
                    break
                row.update(status="recorded", result=result, missing_reason=None)
                if result["status"] != "completed" or result["error"]:
                    row["missing_reason"] = "trial_held_or_incomplete"
                    stop_reason = row["missing_reason"]
                _counts(report)
                _write(path, report)
                if stop_reason:
                    break
        except asyncio.CancelledError:
            for row in report["rows"]:
                if row["status"] == "dispatching":
                    row.update(status="unknown", missing_reason="worker_cancelled")
                elif row["status"] == "planned":
                    row.update(status="not_started", missing_reason="worker_cancelled")
            report["status"] = "interrupted"
            _counts(report)
            _write(path, report)
            raise
        for row in report["rows"]:
            if row["status"] == "planned":
                row.update(status="not_started", missing_reason=stop_reason or "not_started")
        report["status"] = "partial" if stop_reason else "completed"
        _counts(report)
        _write(path, report)
        return _clone(report)
    finally:
        _unlock(fd)


async def run_study(state_root, plan: dict, *, max_model_calls: int, confirm: bool, run_trial: TrialDriver) -> dict:
    admitted = create_study(state_root, plan, max_model_calls=max_model_calls, confirm=confirm)
    return await execute_study(state_root, admitted["study_id"], run_trial=run_trial)
