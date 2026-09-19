"""Explicitly approved, observation-only probes; no coordinator or control executor."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from peb.contracts import Limits, ModelMessage
from peb.providers.anthropic import AnthropicProvider
from peb.rt_contracts import SCHEMA, Decision, RTModelRequest
from peb.runtime.realtime.coordinator import ident
from peb.runtime.realtime.prompt import SYSTEM, prompt_observation


async def main(args):
    if not args.confirm_hosted:
        raise SystemExit("Requires an explicit call budget, with 60-second diagnostic deadlines.")
    raw = (args.bundle / "owner-bundle.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (args.bundle / "SHA256SUMS").read_text().split()[0]:
        raise ValueError("bundle_digest_mismatch")
    bundle = json.loads(raw)
    first = next(
        json.loads(r["payload"])
        for r in bundle["tables"]["rt_records"]
        if r["kind"] == "provider_request"
    )
    plant_messages = first["messages"]
    if args.current_prompt:
        payload = json.loads(next(m["content"] for m in plant_messages if m["role"] == "user"))
        if "observation_encoding" in payload:
            raise ValueError("requires_original_observation_encoding")
        payload["observation"] = prompt_observation(payload["observation"])
        payload["observation_encoding"] = "column_tables_v1"
        plant_messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, separators=(",", ":"))},
        ]
    inputs = [
        (
            "minimal_transport",
            [{"role": "user", "content": 'Return only this JSON object: {"ok":true}'}],
            128,
        ),
        (
            "updated_plant_observation" if args.current_prompt else "archived_plant_observation",
            plant_messages,
            1024,
        ),
    ]
    if args.plant_only:
        if not args.current_prompt:
            raise ValueError("plant_only_requires_current_prompt")
        inputs = [
            (f"updated_plant_observation_{n}", plant_messages, 1024)
            for n in range(1, args.attempts + 1)
        ]
    elif args.attempts != 2:
        raise ValueError("attempt_count_requires_plant_only")
    args.out.mkdir(parents=True, exist_ok=False)
    provider = AnthropicProvider(args.model, thinking=args.thinking)
    results = []
    try:
        for label, messages, cap in inputs:
            if sum(len(m["content"]) for m in messages) > 60000:
                raise ValueError("input_limit_exceeded")
            request = RTModelRequest(
                run_id=ident("probe"),
                subject_session_id=ident("subject"),
                step=len(results) + 1,
                provider_kind="anthropic",
                model=args.model,
                messages=[ModelMessage(**m) for m in messages],
                response_schema={"$defs": SCHEMA["$defs"], "$ref": "#/$defs/SubjectDecision"}
                if args.current_prompt and label != "minimal_transport"
                else None,
                limits=Limits(
                    max_model_calls=1,
                    max_output_tokens=cap,
                    request_timeout_s=60,
                    decision_ceiling_bytes=16384,
                ),
                input_hash=hashlib.sha256(
                    json.dumps(messages, sort_keys=True).encode()
                ).hexdigest(),
            )
            result = {
                "label": label,
                "model": args.model,
                "thinking": args.thinking,
                "prompt_format": "current" if args.current_prompt else "archived",
                "input_hash": request.input_hash,
                "max_output_tokens": cap,
                "deadline_s": 60,
                "observation_only": True,
                "plant_effects": 0,
            }
            # Record the attempt before sending; retries are disabled in the adapter.
            (args.out / (label + ".request.json")).write_text(
                request.model_dump_json(indent=2) + "\n"
            )
            try:
                async with asyncio.timeout(60):
                    response = await provider.generate(request)
                result["response"] = response.model_dump(mode="json")
                if label != "minimal_transport":
                    try:
                        decision = Decision.parse(response.content)
                        result["decision_validation"] = {
                            "valid": response.error is None,
                            "kind": decision.kind,
                        }
                    except (ValueError, TypeError):
                        result["decision_validation"] = {
                            "valid": False,
                            "reason": "invalid_SubjectDecision",
                        }
                    result["operational_readiness_sample"] = (
                        result["decision_validation"]["valid"]
                        and response.duration_ms is not None
                        and response.duration_ms <= 12000
                    )
            except TimeoutError:
                result["error"] = "diagnostic_deadline"
            result["diagnostics"] = provider.diagnostics()
            results.append(result)
            (args.out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps({k: v for k, v in result.items() if k != "response"}), flush=True)
            # An unchanged rejected request will not establish latency/readiness.
            if result["diagnostics"].get("http_status") == 400:
                break
    finally:
        await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--attempts", type=int, choices=[1, 2], default=2)
    parser.add_argument("--plant-only", action="store_true")
    parser.add_argument("--current-prompt", action="store_true")
    parser.add_argument("--thinking", choices=["default", "disabled"], default="default")
    parser.add_argument("--confirm-hosted", action="store_true")
    asyncio.run(main(parser.parse_args()))
