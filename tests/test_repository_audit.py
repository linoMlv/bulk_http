"""Guardrail: the versioned tree must contain no internal references."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORBIDDEN = r"cahier des charges|co-authored-by|generated with \[claude|anthropic"


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def test_no_planning_or_memory_artifacts_are_tracked() -> None:
    tracked = _tracked_files()
    assert "PRD.md" not in tracked
    assert "PROMPT.md" not in tracked
    assert not any(name.startswith("spikes/") for name in tracked)
    assert not any("bulk_http_mem" in name for name in tracked)


def test_no_internal_references_in_tracked_content() -> None:
    result = subprocess.run(
        ["git", "grep", "-In", "-iE", FORBIDDEN, "--", ".", ":!.gitignore"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # git grep exits 1 (no matches) when clean; 0 means it found something.
    assert result.returncode != 0, f"internal references found:\n{result.stdout}"


def test_gitignore_excludes_sensitive_paths() -> None:
    gitignore = (REPO / ".gitignore").read_text()
    for pattern in ("bulk_http_mem/", "source_docs/", "spikes/", "*.ckpt", "out/"):
        assert pattern in gitignore
