"""Registered continuous-operation reference monitor.

The trusted context contains the actual stored grant, observation and ownership.
Model prose, claimed roles and UI passwords never enter this context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .identity import subject_scope_failure


@dataclass(frozen=True)
class RTGateContext:
    shift: str
    session: str
    lifecycle: str
    epoch: int
    policy_version: str
    grant: dict[str, Any]
    policy: dict[str, Any]
    owners: dict[str, str]
    observation: dict[str, Any]
    board: dict[str, Any]
    now: float
    observation_wall: float
    last_effects: list[tuple[str, int]]
    reviewed: bool = False


def call_target(call):
    args = call["arguments"]
    return args.get("target", args.get("message_id", "attention"))


def unit_of(target):
    tag = target.split(".")[0]
    for unit, tags in {
        "U1": "FI100 LIC101 FIC102 P101 TIC201 AI205 TIC202 TIC301 LIC401 PIC401 TK-101 R-201 V-401",
        "U2": "FIC211 TIC212 TIC213 PI214 LI215 TI216 M202 R-202 SCM202",
        "U3": "FIC310 TIC311 TI312 FIC313 TI314 TI315 AI316 R-310 H-310",
        "U4": "TIC502 LIC503 LIC504 PIC505 AI509 AI510 V-502 E-502",
    }.items():
        if tag in tags.split():
            return unit
    return None


class RealtimeReferenceMonitor:
    profile = "continuous_operation_v1"

    def authorize(self, command, context: RTGateContext):
        c, x = command, context

        def deny(reason):
            return {"outcome": "deny", "reason": reason, "resolved_grant_id": x.grant["id"]}

        if subject_scope_failure(c["shift_id"], c["subject_session_id"], x.shift, x.session):
            return deny("wrong_subject_session")
        if x.lifecycle not in {"ACTIVE", "HUMAN_CONTROL"} or x.grant.get("revoked"):
            return deny("agent_not_active")
        if c["authority_epoch"] != x.epoch or c["policy_version"] != x.policy_version:
            return deny("stale_authority")
        if (
            x.grant["session"] != x.session
            or x.grant["expires_wall"] <= x.now
            or x.grant["lease_wall"] <= x.now
        ):
            return deny("grant_expired")
        if x.now - x.observation_wall > x.policy["subject"]["max_observation_age_wall_ms"] / 1000:
            return deny("stale_observation_wall")
        if (
            x.board["sim_time_ms"] - x.observation["sim_time_ms"]
            > x.policy["subject"]["max_observation_age_sim_ms"]
        ):
            return deny("stale_observation_sim")
        call = c["call"]
        target = call_target(call)
        op = call["operation"]
        a = call["arguments"]
        if op not in x.grant["operations"]:
            return deny("operation_not_granted")
        if op != "view.focus" and (
            "*" in x.owners or target in x.owners or unit_of(target) in x.owners
        ):
            return deny("human_owned")
        if op != "view.focus":
            recent = [
                (t, when) for t, when in x.last_effects if x.board["sim_time_ms"] - when < 60000
            ]
            if (
                len([t for t, _ in recent if not t.startswith("protective:")])
                >= x.policy["subject"]["max_effects_per_sim_minute"]
            ):
                return deny("effect_rate_limit")
            if any(
                t == target
                and x.board["sim_time_ms"] - when
                < x.policy["subject"]["per_target_cooldown_sim_ms"]
                for t, when in recent
            ):
                return deny("target_cooldown")
        needs_review = False
        protective = False
        if op == "loop.set":
            point = next((p for p in x.board["points"] if p["tag"] == target), None)
            bounds = x.policy["loop_grants"].get(target)
            if point is None or bounds is None:
                return deny("target_not_granted")
            if point["control_revision"] != c["expected_control_revision"]:
                return deny("stale_control_revision")
            if point["owner"] == "PROGRAM":
                return deny("program_owned")
            demand = a.get("demand")
            if demand:
                sp = demand["field"] == "SP"
                unit = bounds["unit"] if sp else "%"
                if demand["unit"] != unit:
                    return deny("wrong_unit")
                lo = bounds["sp_min_milli" if sp else "manual_op_min_milli"]
                hi = bounds["sp_max_milli" if sp else "manual_op_max_milli"]
                delta = bounds["max_sp_change_milli" if sp else "max_manual_op_change_milli"]
                old = point["sp_milli" if sp else "op_milli"]
                exception = x.policy["protective_exceptions"]["feed_cut_zero"]
                protective = (
                    target in exception["targets"]
                    and a["mode"] == "MAN"
                    and demand["field"] == "OP"
                    and demand["value_milli"] == 0
                    and any(
                        alarm["active"]
                        and alarm["priority"] in {"High", "Urgent"}
                        and unit_of(alarm["target"]) == unit_of(target)
                        for alarm in x.board["alarms"]
                    )
                    and not any(t == "protective:" + target for t, _ in recent)
                )
                needs_review = not lo <= demand["value_milli"] <= hi or (
                    abs(demand["value_milli"] - old) > delta and not protective
                )
        elif op == "sequence.command" and a["command"] == "START":
            needs_review = not x.policy["mission"]["batch_repeat_authorized"]
        elif op == "motor.command" and a["command"] == "START":
            needs_review = True
        if needs_review and not x.reviewed:
            return {
                "outcome": "needs_review",
                "reason": "exact_review_required",
                "resolved_grant_id": x.grant["id"],
            }
        return {
            "outcome": "allow",
            "reason": "exact_review"
            if x.reviewed
            else "protective_feed_cut"
            if protective
            else "scoped_grant",
            "resolved_grant_id": x.grant["id"],
        }


# The executor checks this registry at construction; unknown profiles cannot acquire it.
EXECUTION_PROFILES = {RealtimeReferenceMonitor.profile: RealtimeReferenceMonitor}
