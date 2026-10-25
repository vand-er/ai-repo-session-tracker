"""Test package. Points the app at a throwaway Workspace file before any test runs,
so no test can read or write the owner's real one. Also makes `tests/` a git ceiling, so a
scan of a fixture folder never finds this project's own repo and its main branch's commit
subjects (src/model/main_branch.py); the git repos tests make live in temp folders."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

from src.workspace import ENV_VAR

_TMP = tempfile.mkdtemp(prefix="wayfinder-board-tests-")
os.environ[ENV_VAR] = str(Path(_TMP) / "workspace.json")
# The default projects folder is `~/.claude/projects` unless this is set: tests that want
# it set it themselves, so a machine that has it gives the same defaults as one without.
os.environ.pop("CLAUDE_CONFIG_DIR", None)
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

FIXTURES = Path(__file__).parent / "fixtures"

os.environ["GIT_CEILING_DIRECTORIES"] = os.pathsep.join(
    p for p in (os.environ.get("GIT_CEILING_DIRECTORIES"), str(Path(__file__).parent)) if p)
