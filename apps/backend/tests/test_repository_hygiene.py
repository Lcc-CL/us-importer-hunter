"""Repository hygiene guards for committed temporary smoke artifacts."""

import subprocess
from pathlib import Path


def test_tracked_files_exclude_temporary_smoke_artifacts() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_files = result.stdout.splitlines()

    assert not any("/private/tmp/" in f"/{path}" for path in tracked_files)
    assert not any(Path(path).name == "smoke.py" for path in tracked_files)
    assert not any(path.endswith(".dump") for path in tracked_files)
