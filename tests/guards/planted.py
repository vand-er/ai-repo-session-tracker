"""Planted violations: the repo's tree with extra files laid over it, in memory.

Every guard takes the root of a tree, so it runs on the real repo (`REPO`) and on a
planted tree alike. A guard's planted-violation case looks like:

    with planted_tree({"src/model/bad.py": "import src.workspace\\n"}) as root:
        self.assertIn("src.model.bad", " ".join(my_guard(root)))

Paths are relative to the repo root and use forward slashes. A planted file replaces any
file already at its path, so a case can also edit a real module; `None` removes the file.
Nothing is written to disk (see `tree.py`): a guard reads the planted files from memory,
and one that imports the tree serves them from memory in its fresh interpreter.
"""

from contextlib import contextmanager

from tests.guards.tree import REPO, Tree

__all__ = ["REPO", "planted_tree"]


@contextmanager
def planted_tree(files):
    """Yield the repo's tree with each `{path: text}` in `files` laid over it."""
    yield Tree(REPO, files)
