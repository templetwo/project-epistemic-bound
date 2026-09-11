"""Measure a committed checkout and fail closed on incomplete release evidence.

No model commands, credentials, downloads of models, publishing or tagging.
Dependency installation uses the committed uv.lock. Matrix coverage is a reviewed
human declaration; validating its shape cannot establish the adequacy of a test.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("Unrecognized JUnit root")
    cases = list(root.iter("testcase"))
    counts = {"collected": len(cases), "passed": 0, "failed": 0, "skipped": 0}
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            counts["failed"] += 1
        elif case.find("skipped") is not None:
            counts["skipped"] += 1
        else:
            counts["passed"] += 1
    # Do not trust only the declared aggregate: testcase records are authoritative.
    return counts


def matrix_findings(checkout: Path) -> tuple[list[str], dict[str, str]]:
    expected = set(re.findall(r"^\| ([A-Z]+-\d{2}) \|", (checkout / "BUILD_SPEC.md").read_text(), re.MULTILINE))
    if not expected:
        return ["No acceptance IDs found in BUILD_SPEC.md"], {}
    matrix_path = checkout / "docs/acceptance-matrix.json"
    matrix = json.loads(matrix_path.read_text())
    if matrix.get("schema_version") != 1 or not isinstance(matrix.get("gates"), list):
        return ["Invalid acceptance matrix schema"], {}
    rows = matrix["gates"]
    ids = [row.get("id") for row in rows]
    findings = []
    artifacts = {"docs/acceptance-matrix.json": digest(matrix_path)}
    if len(ids) != len(set(ids)) or set(ids) != expected:
        findings.append("Matrix IDs must cover every BUILD_SPEC acceptance ID exactly once")
    for row in rows:
        label = str(row.get("id"))
        if row.get("status") != "passed":
            findings.append(f"{label}: {row.get('status', 'missing status')}")
            continue
        if not row.get("reviewed_by") or not row.get("evidence"):
            findings.append(f"{label}: passing declaration requires reviewer and evidence")
            continue
        for name in row["evidence"]:
            relative = Path(name)
            path = checkout / relative
            if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(checkout.resolve()) or not path.is_file():
                findings.append(f"{label}: missing or unsafe evidence path")
            else:
                artifacts[name] = digest(path)
    return findings, artifacts


def release_findings(counts: dict[str, int], commands: list[dict], matrix: list[str]) -> list[str]:
    findings = list(matrix)
    if counts["collected"] == 0 or counts["passed"] == 0:
        findings.append("No passing tests collected")
    if counts["failed"]:
        findings.append("Deterministic tests failed")
    if counts["skipped"]:
        findings.append("Required suite contains skipped tests; release remains blocked")
    for command in commands:
        if command["exit_code"] != 0:
            findings.append(f"Command failed: {command['name']} ({command['exit_code']})")
    if not any(command["name"] == "pytest" for command in commands):
        findings.append("Pytest did not run")
    if not any(command["name"] == "ruff" for command in commands):
        findings.append("Lint did not run")
    return findings


def run_command(name: str, command: list[str], checkout: Path, output: Path, env: dict[str, str]) -> dict:
    stdout, stderr = output / f"{name}.stdout.txt", output / f"{name}.stderr.txt"
    started = utc_now()
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            result = subprocess.run(command, cwd=checkout, env=env, stdout=out, stderr=err, timeout=180, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
            err.write(b"Release-check command exceeded 180 seconds.\n")
        except OSError as exc:
            code = 127
            err.write(f"Unable to start command: {type(exc).__name__}\n".encode())
    return {"name": name, "command": command, "started_at": started, "finished_at": utc_now(),
            "exit_code": code, "stdout": stdout.name, "stderr": stderr.name,
            "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Exact committed tree to archive and test")
    parser.add_argument("--output", type=Path, required=True, help="New receipt directory outside the repository")
    args = parser.parse_args()
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    commit = subprocess.check_output(["git", "rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}"], cwd=repo, text=True).strip()
    output = args.output.expanduser().resolve()
    if output.is_relative_to(repo.resolve()):
        parser.error("--output must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)  # never overwrite an earlier receipt
    started = utc_now()
    counts = {"collected": 0, "passed": 0, "failed": 0, "skipped": 0}
    commands, problems, artifacts = [], [], {}
    environment = {"platform": platform.platform(), "checker_python": platform.python_version(),
                   "dependency_lock": "uv.lock", "state": "temporary; no model execution requested"}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="peb-release-") as temporary:
        checkout = Path(temporary) / "checkout"
        checkout.mkdir()
        archive = subprocess.check_output(["git", "archive", "--format=tar", commit], cwd=repo)
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(checkout, filter="data")
        env = dict(os.environ)
        env.pop("DEEPSEEK_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        env["PEB_STATE_ROOT"] = str(Path(temporary) / "state")
        env["PEB_OLLAMA_ENDPOINT"] = "http://127.0.0.1:9"
        env["PEB_OLLAMA_MODEL"] = ""
        try:
            problems, artifacts = matrix_findings(checkout)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            problems.append(f"Acceptance matrix unreadable: {type(exc).__name__}")
        commands.append(run_command("sync", ["uv", "sync", "--locked"], checkout, output, env))
        if commands[-1]["exit_code"] == 0:
            commands.append(run_command("uv-version", ["uv", "--version"], checkout, output, env))
            commands.append(run_command("packages", ["uv", "pip", "list", "--format", "json"], checkout, output, env))
            commands.append(run_command("versions", ["uv", "run", "--locked", "python", "--version"], checkout, output, env))
            commands.append(run_command("ruff", ["uv", "run", "--locked", "ruff", "check", "."], checkout, output, env))
            commands.append(run_command("pytest", ["uv", "run", "--locked", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", f"--junitxml={output / 'junit.xml'}"], checkout, output, env))
            try:
                counts = junit_counts(output / "junit.xml")
            except (OSError, ValueError, ET.ParseError) as exc:
                problems.append(f"JUnit missing or invalid: {type(exc).__name__}")
        artifacts["uv.lock"] = digest(checkout / "uv.lock")
        artifacts["BUILD_SPEC.md"] = digest(checkout / "BUILD_SPEC.md")
    findings = release_findings(counts, commands, problems)
    primary = next((c for c in commands if c["name"] == "pytest"), commands[-1])
    receipt = {"schema_version": 1, "kind": "software_verification_receipt", "project": "project-epistemic-bound",
               "commit": commit, "working_tree": "clean git archive of committed tree", "command": primary["command"],
               "started_at": started, "finished_at": utc_now(), "exit_code": primary["exit_code"],
               "release_exit_code": 1 if findings else 0, "release_status": "blocked" if findings else "passed",
               "tests": counts, "environment": "environment.json", "stdout_sha256": primary["stdout_sha256"],
               "stderr_sha256": primary["stderr_sha256"],
               "junit_sha256": digest(output / "junit.xml") if (output / "junit.xml").exists() else None,
               "checker_sha256": digest(Path(__file__)), "commands": commands, "evidence_sha256": artifacts,
               "limits": findings, "evidence_policy": "Matrix declarations require human review; this tool validates completeness and file presence, not semantic sufficiency. All suite skips block release."}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"commit": commit, "tests": counts, "release_status": receipt["release_status"],
                      "open_findings": len(findings), "receipt": str(output / "receipt.json")}, indent=2))
    return receipt["release_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
