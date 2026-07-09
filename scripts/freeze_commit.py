#!/usr/bin/env python3
"""Freeze the current git commit hash into pykmhelpers/_commit.py before packaging a release."""

import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMIT_FILE = REPO_ROOT / "pykmhelpers" / "_commit.py"


def main() -> None:
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()
    COMMIT_FILE.write_text(
        '"""Git commit this release/build was made from. '
        'Frozen by scripts/freeze_commit.py before packaging."""\n\n'
        f'GIT_COMMIT = "{commit}"\n'
    )
    print(f"Froze GIT_COMMIT = {commit} into {COMMIT_FILE}")


if __name__ == "__main__":
    main()