"""Bounded development study schedules (EVAL-02); planning never runs a provider.

Stable SHA256 ordering makes the recorded seed reproducible without depending on
Python random's implementation. Each trial requires a fresh run/session/workspace.
The output is a plan, not proof that trials ran or that a provider is available.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..boundary.canonical import DOMAIN_SNAPSHOT, digest
from ..contracts import StrictModel, strict_json_loads
from ..runtime.profiles import load_profile, require_runnable
from ..workspace.fixtures import (
    FIXTURE_PATHS,
    FIXTURE_ROOT,
    FRAMES,
    load_fixture,
    validate_frame_set,
)

PLANNER_VERSION = "framing-schedule-v1"
FRAMING_PROFILES = frozenset({"baseline", "tone_only", "contract_only", "placebo"})


class StudyConfig(StrictModel):
    schema_version: Literal[1]
    seed: int = Field(ge=0, le=2**63 - 1)
    fixture_ids: list[str] = Field(min_length=1, max_length=6)
    frames: list[Literal["ordinary", "game", "roleplay", "evaluation"]] = Field(min_length=1, max_length=4)
    profile_ids: list[str] = Field(min_length=1, max_length=4)
    repeats: int = Field(ge=1, le=20)
    provider: Literal["ollama", "deepseek", "scripted"]
    model: str = Field(min_length=1, max_length=200)
    thinking: Literal["enabled", "disabled"] = "enabled"
    max_model_calls_per_trial: int = Field(ge=1, le=64)
    max_output_tokens: int = Field(ge=64, le=32768)
    max_trials: int = Field(ge=1, le=512)
    max_total_model_calls: int = Field(ge=1, le=32768)

    @model_validator(mode="after")
    def validate_schedule(self):
        for name in ("fixture_ids", "frames", "profile_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} contains duplicates")
        if set(self.fixture_ids) - FIXTURE_PATHS.keys():
            raise ValueError("Only registered development fixtures are supported")
        if set(self.profile_ids) - FRAMING_PROFILES:
            raise ValueError("Initial framing study supports A0..A3 only; candidate ablations require a separate plan")
        if not self.model.strip() or (self.provider == "scripted" and self.model != "scripted"):
            raise ValueError("Explicit model required; scripted provider must use model=scripted")
        count = len(self.fixture_ids) * len(self.frames) * len(self.profile_ids) * self.repeats
        if count > self.max_trials or count * self.max_model_calls_per_trial > self.max_total_model_calls:
            raise ValueError("Requested schedule exceeds the explicit trial or model-call cap")
        return self


def build_plan(config: dict) -> dict:
    """Validate explicit selections and return a detached JSON-ready plan; no writes/network."""
    cfg = StudyConfig.model_validate_json(json.dumps(config))
    profiles = {pid: require_runnable(load_profile(pid)) for pid in cfg.profile_ids}
    if any(p.placeholder or str(p.preaction_protocol) != "observe" for p in profiles.values()):
        raise ValueError("Framing arms require runnable, non-placeholder text with protocol=observe")
    fixtures = {fid: load_fixture(fid) for fid in cfg.fixture_ids}
    snapshots = {}
    for fid, fixture in fixtures.items():
        invariant = validate_frame_set([fixture.frame_case(frame) for frame in FRAMES])
        path = FIXTURE_ROOT / FIXTURE_PATHS[fid]
        frame = fixture.frame_case("ordinary")
        snapshots[fid] = {"fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "frame_invariant_hash": invariant,
                          "task_hash": digest(DOMAIN_SNAPSHOT, frame["public_task"]),
                          "environment_hash": digest(DOMAIN_SNAPSHOT, frame["environment"]),
                          "tools_hash": frame["tool_schema_hash"],
                          "grants_hash": digest(DOMAIN_SNAPSHOT, frame["actual_grants"]),
                          "consequence_hash": digest(DOMAIN_SNAPSHOT, frame["consequence_model"])}
    profile_records = {pid: {"profile_hash": p.hash, "arm": p.arm, "status": p.status,
                             "characters": p.chars, "words": p.words, "source": p.source}
                       for pid, p in profiles.items()}
    trials = []
    for fid, pid, frame, repeat in itertools.product(sorted(fixtures), sorted(profiles), sorted(cfg.frames), range(cfg.repeats)):
        identity = {"fixture_id": fid, "profile_id": pid, "frame": frame, "repeat": repeat}
        trial_id = "trial_" + digest(DOMAIN_SNAPSHOT, identity)[:32]
        pair_id = "pair_" + digest(DOMAIN_SNAPSHOT, {"fixture_id": fid, "repeat": repeat})[:32]
        condition = {"provider": cfg.provider, "model": cfg.model, "thinking": cfg.thinking,
                     "preaction_protocol": "observe", "max_model_calls": cfg.max_model_calls_per_trial,
                     "max_output_tokens": cfg.max_output_tokens, **snapshots[fid],
                     "profile_hash": profiles[pid].hash}
        trials.append({**identity, "trial_id": trial_id, "pair_id": pair_id,
                       "condition_hash": digest(DOMAIN_SNAPSHOT, condition), "status": "planned"})
    trials.sort(key=lambda row: hashlib.sha256(f"{cfg.seed}:{row['trial_id']}".encode()).digest())
    for index, row in enumerate(trials):
        row["ordinal"] = index
    plan = {"schema_version": 1, "planner_version": PLANNER_VERSION, "ordering": "sha256-sort-v1",
            "config": cfg.model_dump(mode="json"), "dataset_split": "development",
            "mode": "scripted_validation" if cfg.provider == "scripted" else "model_observation",
            "fixtures": snapshots, "profiles": profile_records, "trials": trials,
            "counts": {"planned": len(trials), "started": 0, "provider_completed": 0, "evaluable": 0},
            "budget": {"model_calls_ceiling": len(trials) * cfg.max_model_calls_per_trial,
                       "output_tokens_ceiling": len(trials) * cfg.max_model_calls_per_trial * cfg.max_output_tokens,
                       "probe_requests_note": "Provider readiness probes are separate from decision calls; no probe made at plan."},
            "reset_policy": "fresh run_id, subject_session_id, workspace, grants and empty subject history for every trial",
            "provider_seed_support": "not_verified; schedule seed does not imply deterministic model sampling",
            "limitations": ["Development fixtures are public to builders; no held-out or blind evaluation.",
                            "A plan makes no provider-availability, execution or behavioral claim.",
                            "Trials sharing pair_id are matched observations, not independent replicates.",
                            "Condition hashes omit only presentation frame and repetition; differing hashes are not pooled."]}
    plan["plan_hash"] = digest(DOMAIN_SNAPSHOT, plan)
    plan["study_id"] = "study_" + plan["plan_hash"][:32]
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="New plan file; never overwrite an existing plan")
    args = parser.parse_args()
    plan = build_plan(strict_json_loads(args.config.read_text()))
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.out:
        with args.out.open("x") as output:
            output.write(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
