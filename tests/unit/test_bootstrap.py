"""BOOT-01 / BOOT-02 (BUILD_SPEC §4): the S0 bootstrap against temporary directories only.

BOOT-01: a fresh workspace becomes the intended repo + worktrees, private documents untracked, no remote.
BOOT-02: an existing destination, a symlinked source, a source inside a repo, or a branch/path conflict
         STOPs before anything is moved, initialized, staged or forced; a rerun reuses the established repo.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.sh"


def run(cmd: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, **env, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x", "HOME": env.get("HOME", os.environ.get("HOME", "/"))}
    return subprocess.run(["bash", str(SCRIPT), cmd, *args], env=full, capture_output=True, text=True, check=False)


@pytest.fixture
def ws(tmp_path: Path) -> dict[str, str]:
    desktop = tmp_path / "Desktop"
    src = desktop / "untitled"
    src.mkdir(parents=True)
    (src / "BUILD_SPEC.md").write_text("# spec\n")
    (src / "TEAM_START.md").write_text("# team\n")
    (src / "Private_Contract.docx").write_bytes(b"PK\x03\x04private")  # must never be staged
    (src / "notes.pdf").write_bytes(b"%PDF-private")
    return {"HOME": str(tmp_path), "PEB_SRC": str(src), "PEB_ROOT": str(desktop / "project-epistemic-bound"),
            "PEB_WT": str(desktop / "project-epistemic-bound-worktrees")}


def git(root: str, *args: str) -> str:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True).stdout.strip()


def test_boot_01_fresh_workspace_becomes_the_repo_with_private_documents_untracked_and_no_remote(ws):
    r = run("init", ws, "BUILD_SPEC.md", "TEAM_START.md")
    assert r.returncode == 0, r.stdout + r.stderr
    root = ws["PEB_ROOT"]
    assert not Path(ws["PEB_SRC"]).exists() and Path(root, "BUILD_SPEC.md").is_file()
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(root, "remote") == ""  # no remote, ever
    tracked = set(git(root, "ls-files").splitlines())
    assert tracked == {".gitignore", "BUILD_SPEC.md", "TEAM_START.md"}
    assert Path(root, "Private_Contract.docx").exists() and Path(root, "notes.pdf").exists()  # preserved on disk
    assert git(root, "check-ignore", "Private_Contract.docx") == "Private_Contract.docx"  # and ignored
    assert git(root, "status", "--porcelain") == ""
    # a rerun inspects and reuses; nothing moves, nothing is re-initialized, nothing is staged
    head = git(root, "rev-parse", "HEAD")
    r2 = run("init", ws, "BUILD_SPEC.md")
    assert r2.returncode == 0 and "reusing" in r2.stdout and git(root, "rev-parse", "HEAD") == head
    assert not Path(root, ".git", ".git").exists()
    # worktrees: three lanes, then a rerun reuses them
    r3 = run("worktrees", ws)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    listed = git(root, "worktree", "list", "--porcelain")
    for br in ("build/claude-core", "build/grok-boundary", "build/codex-workroom"):
        assert f"branch refs/heads/{br}" in listed
    r4 = run("worktrees", ws)
    assert r4.returncode == 0 and r4.stdout.count("reusing") == 3


def test_boot_01_refuses_to_stage_a_private_document_even_when_named(ws):
    r = run("init", ws, "BUILD_SPEC.md", "Private_Contract.docx")
    assert r.returncode == 1 and "refusing to stage an ignored (private) path" in r.stdout
    root = ws["PEB_ROOT"]
    assert Path(root).is_dir()  # the rename happened before the staging check…
    assert git(root, "ls-files") == ""  # …but nothing was committed or staged
    assert git(root, "remote") == ""


@pytest.mark.parametrize("case", ["destination_exists", "destination_symlink", "source_symlink", "source_in_repo",
                                  "missing_spec"])
def test_boot_02_unexpected_state_stops_before_any_change(ws, case):
    src, root = Path(ws["PEB_SRC"]), Path(ws["PEB_ROOT"])
    if case == "destination_exists":
        root.mkdir()
        (root / "keep.txt").write_text("existing")
    elif case == "destination_symlink":
        target = root.parent / "elsewhere"
        target.mkdir()
        root.symlink_to(target)
    elif case == "source_symlink":
        real = src.parent / "real-untitled"
        src.rename(real)
        src.symlink_to(real)
    elif case == "source_in_repo":
        subprocess.run(["git", "-C", str(src), "init", "-q", "-b", "main"], check=True)
    elif case == "missing_spec":
        (src / "BUILD_SPEC.md").unlink()
    before = sorted(p.name for p in src.parent.iterdir())
    r = run("init", ws, "BUILD_SPEC.md")
    assert r.returncode == 1 and r.stdout.startswith("STOP:"), r.stdout + r.stderr
    assert sorted(p.name for p in src.parent.iterdir()) == before  # nothing moved
    if case == "destination_exists":
        assert (root / "keep.txt").read_text() == "existing" and not (root / ".git").exists()
    if case not in ("source_in_repo",):
        assert not (src / ".git").exists() if src.is_dir() else True  # no repo was initialized in the source


def test_boot_02_worktree_conflicts_are_inspected_not_forced(ws):
    assert run("init", ws, "BUILD_SPEC.md").returncode == 0
    root = ws["PEB_ROOT"]
    subprocess.run(["git", "-C", root, "branch", "build/grok-boundary"], check=True)  # branch exists, no worktree
    r = run("worktrees", ws)
    assert r.returncode == 1 and "do not --force" in r.stdout
    assert "build/claude-core" in git(root, "worktree", "list", "--porcelain")  # the first lane was created…
    assert not Path(ws["PEB_WT"], "grok").exists()  # …the conflicting one was not forced
    subprocess.run(["git", "-C", root, "branch", "-D", "build/grok-boundary"], check=True)
    Path(ws["PEB_WT"], "codex").mkdir(parents=True)  # path exists without its branch
    r2 = run("worktrees", ws)
    assert r2.returncode == 1 and "path exists without its branch" in r2.stdout
