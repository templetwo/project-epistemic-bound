"""A CockpitTransport for tests: in-memory runs and events, every call recorded, no network, no store."""
from __future__ import annotations

from typing import Any

from peb.tui.transport import EventPage, TransportError


def event(seq: int, kind: str, prev: str | None, actor: str = "subject", payload: dict | None = None) -> dict:
    return {"seq": seq, "event_type": kind, "prev_hash": prev, "event_hash": f"h{seq}", "actor": actor,
            "ts": f"2026-09-12T00:00:{seq:02d}+00:00", "payload": payload or {}}


class FakeTransport:
    base_url = "http://127.0.0.1:8787"

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.runs: dict[str, dict[str, Any]] = {}
        self.events_by_run: dict[str, list[dict]] = {}
        self.fail_reads = False
        self.closed = False

    def add_run(self, run_id: str, status: str = "running", *, events: list[dict] | None = None, reviews: list[dict] | None = None,
                grants: list[dict] | None = None, commitments: list[dict] | None = None, model: str = "scripted") -> None:
        self.runs[run_id] = {"run_id": run_id, "status": status, "mode": "scripted_validation", "created_at": "2026-09-12T00:00:00+00:00",
                             "manifest": {"run_id": run_id, "provider_kind": "scripted", "model_requested": model, "model_resolved": None,
                                          "profile_id": "baseline", "task_id": "conceal-error-basic", "limits": {"max_model_calls": 16},
                                          "settings": {"frame": "ordinary", "arm": "A0"}},
                             "reviews": reviews or [], "grants": grants or [], "commitments": commitments or []}
        self.events_by_run[run_id] = list(events or [event(0, "run_created", None, "supervisor")])

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))

    def _read(self, name: str, *args: Any) -> None:
        self._record(name, *args)
        if self.fail_reads:
            raise TransportError(0, "provider_unavailable", "workroom unreachable: fake")

    async def sign_in(self, secret: str) -> None:
        self._record("sign_in")

    async def sign_out(self) -> None:
        self._record("sign_out")

    async def health(self) -> dict[str, Any]:
        self._read("health")
        return {"storage": {"status": "ok"}, "provider": {"status": "server_unreachable"}}

    async def list_runs(self) -> dict[str, Any]:
        self._read("list_runs")
        return {"runs": [{k: r[k] for k in ("run_id", "status", "mode", "created_at")} for r in self.runs.values()]}

    async def get_run(self, run_id: str) -> dict[str, Any]:
        self._read("get_run", run_id)
        r = self.runs[run_id]
        return {"status": r["status"], "run": {"manifest": r["manifest"], "events": self.events_by_run[run_id], "grants": r["grants"],
                                                "commitments": r["commitments"]}, "reviews": r["reviews"], "held": {}}

    async def events(self, run_id: str, cursor: int = 0, limit: int = 100) -> EventPage:
        self._read("events", run_id, cursor, limit)
        all_events = self.events_by_run[run_id]
        page = all_events[cursor:cursor + limit]
        nxt = cursor + len(page)
        return EventPage(events=page, cursor=cursor, next_cursor=nxt if nxt < len(all_events) else None, total=len(all_events))

    async def reviews(self) -> dict[str, Any]:
        self._read("reviews")
        rows = [dict(r, run_id=rid, open=r.get("status") in ("pending", "acknowledged")) for rid, run in self.runs.items() for r in run["reviews"]]
        return {"reviews": rows, "open": sum(1 for r in rows if r["open"]), "total": len(rows)}

    async def profiles(self) -> dict[str, Any]:
        self._read("profiles")
        return {"profiles": []}

    # mutations
    async def demo(self, case: str, frame: str) -> dict[str, Any]:
        self._record("demo", case, frame)
        rid = f"run_{len(self.runs) + 1:032x}"
        self.add_run(rid, "completed", events=[event(0, "run_created", None, "supervisor"), event(1, "model_request", "h0"),
                                                event(2, "model_response", "h1", payload={"prompt_tokens": 5, "completion_tokens": 7})])
        return {"run_id": rid}

    async def preview_run(self, spec):
        self._record("preview_run", spec); return {}

    async def start_run(self, start_payload, preview_token):
        self._record("start_run", start_payload, preview_token); return {}

    async def create_run(self, spec):
        self._record("create_run", spec); return {}

    async def step_run(self, run_id):
        self._record("step_run", run_id); return {"status": "running"}

    async def begin_run(self, run_id):
        self._record("begin_run", run_id); return {"status": "running"}

    async def pause_run(self, run_id, note=""):
        self._record("pause_run", run_id, note); self.runs[run_id]["status"] = "paused"; return {"status": "paused"}

    async def cancel_run(self, run_id, note=""):
        self._record("cancel_run", run_id, note); self.runs[run_id]["status"] = "cancelled"; return {"status": "cancelled"}

    async def resume_run(self, run_id):
        self._record("resume_run", run_id); self.runs[run_id]["status"] = "running"; return {"status": "running"}

    async def resolve_review(self, run_id, review_id, decision, note=""):
        self._record("resolve_review", run_id, review_id, decision, note)
        for r in self.runs[run_id]["reviews"]:
            if r["review_id"] == review_id:
                r["status"] = "acknowledged" if decision == "ack" else f"resolved_{decision}"
        return {"status": "paused"}

    async def accept_commitment(self, run_id, commitment_id, note=""):
        self._record("accept_commitment", run_id, commitment_id, note); return {}

    async def revise_commitment(self, run_id, commitment_id, text, note=""):
        self._record("revise_commitment", run_id, commitment_id, text, note); return {}

    async def verify(self, run_id):
        self._record("verify", run_id)
        self.verify_checked = getattr(self, "verify_checked", None)
        checked = self.verify_checked if self.verify_checked is not None else len(self.events_by_run[run_id])
        return {"run_id": run_id, "verification": {"chain_consistent": True, "summary": "chain_consistent; external_anchor_absent", "failures": [],
                                                  "checked_events": checked},
                "anchor_provenance": "none_external_anchor_absent"}

    async def export(self, run_id, out):
        self._record("export", run_id, out); return {"exported": f"{out}/run-{run_id}"}

    async def plan_study(self, config):
        self._record("plan_study", config); return {}

    async def close(self) -> None:
        self.closed = True

    def mutations(self) -> list[str]:
        reads = {"sign_in", "sign_out", "health", "list_runs", "get_run", "events", "reviews", "profiles"}
        return [name for name, _ in self.calls if name not in reads]
