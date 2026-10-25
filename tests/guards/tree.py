"""The source tree the guards read: the repo on disk, with any planted files laid over it.

Every guard takes `root`: the repo (`REPO`, a path) or a planted `Tree` from
`planted.planted_tree`. A planted file lives in memory only, so a planted case writes and
reads nothing on disk; the repo's own files are read and parsed once per run (`text`,
`parse`). A guard that must import the tree does it in a fresh interpreter
(`start_python`), which serves the planted files from memory too; such checks are
registered with `fresh_check` and all start together, side by side.

The names the guards share live here: `APP` (the app package), `TOOLKITS` (the GUI
toolkits), `source` (a module's file), `within` (is a module in a package) and
`app_modules` (every module of the app, found by walking the package).
"""

import ast
import atexit
import json
import os
import site
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = "src"
TOOLKITS = ("tkinter", "_tkinter", "customtkinter")


class Tree:
    """`base` on disk with `files` laid over it: `{path: text}`, paths relative to `base`
    with forward slashes. A planted file replaces any file at its path; `None` removes it."""

    def __init__(self, base=REPO, files=None):
        self.base = Path(base)
        self.files = dict(files or {})

    def _disk(self, path):
        return self.base / path

    def is_file(self, path):
        if path in self.files:
            return self.files[path] is not None
        return self._disk(path).is_file()

    def is_dir(self, path):
        prefix = path.rstrip("/") + "/"
        return (any(p.startswith(prefix) and t is not None for p, t in self.files.items())
                or self._disk(path).is_dir())

    def text(self, path):
        if path in self.files:
            if self.files[path] is None:
                raise FileNotFoundError(path)
            return self.files[path]
        return _disk_text(*_stamp(self._disk(path)))

    def parse(self, path):
        if path in self.files:
            return ast.parse(self.text(path))
        return _disk_parse(*_stamp(self._disk(path)))

    def paths(self, folder, suffix, recursive=True):
        """Every file under `folder` whose name ends in `suffix`, sorted; `recursive=False`
        looks in `folder` alone."""
        on_disk = self._disk(folder)
        pattern = f"*{suffix}"
        found = {p.relative_to(self.base).as_posix()
                 for p in (on_disk.rglob(pattern) if recursive else on_disk.glob(pattern))}
        prefix = folder.rstrip("/") + "/"
        for path, text in self.files.items():
            inside = path.startswith(prefix) and path.endswith(suffix)
            if inside and (recursive or "/" not in path[len(prefix):]):
                (found.add if text is not None else found.discard)(path)
        return sorted(found)


def tree(root):
    """`root` as a Tree: a planted Tree as it is, a folder as that folder with nothing over it."""
    return root if isinstance(root, Tree) else Tree(root)


def _stamp(path):
    stat = os.stat(path)
    return str(path), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=None)
def _disk_text(path, _mtime_ns, _size):
    with open(path, encoding="utf-8") as file:
        return file.read()


@lru_cache(maxsize=None)
def _disk_parse(path, mtime_ns, size):
    return ast.parse(_disk_text(path, mtime_ns, size))


def within(name, package):
    """Whether module `name` is `package` or inside it."""
    return name == package or name.startswith(package + ".")


def source(root, name):
    """The file of module `name` in `root`, relative to it: `src/a/__init__.py` for a
    package, `src/a.py` for a module."""
    path = name.replace(".", "/")
    return f"{path}/__init__.py" if tree(root).is_dir(path) else f"{path}.py"


def app_modules(root):
    """Every module of the app package under `root`, by dotted name, sorted."""
    names = []
    for path in tree(root).paths(APP, ".py"):
        parts = path[:-len(".py")].split("/")
        if parts[-1] == "__init__":
            parts.pop()
        names.append(".".join(parts))
    return sorted(names)


# The fresh interpreter's start: the tree first on the path, then the site-packages (it
# runs with -S, which skips site's start-up work), then the planted files served from
# memory ahead of anything on disk.
_PRELUDE = """\
import json, sys
_base, _planted, _extra = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
sys.argv[1:] = sys.argv[4:]
sys.path[:0] = [_base]
sys.path.extend(_extra)
if _planted:
    import importlib.abc, importlib.util, os

    class _Planted(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, name, path=None, target=None):
            rel = name.replace(".", "/")
            for file, package in ((rel + "/__init__.py", True), (rel + ".py", False)):
                if file in _planted:
                    if _planted[file] is None:
                        raise ModuleNotFoundError(name)
                    spec = importlib.util.spec_from_loader(name, self, origin=file,
                                                           is_package=package)
                    if package:
                        spec.submodule_search_locations = [os.path.join(_base, rel)]
                    return spec
            return None

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            file = module.__spec__.origin
            exec(compile(_planted[file], file, "exec"), module.__dict__)

    sys.meta_path.insert(0, _Planted())
"""


def start_python(script, root, *args):
    """Start `script` in a fresh, isolated interpreter that imports from `root` (planted
    files included); `sys.argv[1:]` there is `args`. Returns the running process; read
    its result with `finish`."""
    planted = tree(root)
    extra = [p for p in site.getsitepackages() if Path(p).name.lower() == "site-packages"]
    return subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", _PRELUDE + script, str(planted.base),
         json.dumps(planted.files), json.dumps(extra), *args],
        cwd=planted.base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def finish(process, what):
    """The JSON `process` (from `start_python`) printed; raises naming `what` if it failed."""
    out, err = process.communicate()
    if process.returncode:
        raise RuntimeError(f"{what} failed: {err}")
    return json.loads(out)


# The checks that need a fresh interpreter, started side by side: an interpreter's start
# and its imports are most of each one's cost, and the hook must stay fast.
_STARTERS = {}   # key -> start(), registered when a guard's module is imported
_RUNNING = {}    # key -> its running process, until its result is taken


def fresh_check(key, start):
    """Register a check that runs in a fresh interpreter: `start()` starts it and returns
    the process (from `start_python`). Nothing starts now; the first `fresh_started` starts
    every registered check at once."""
    _STARTERS[key] = start


def fresh_started(key):
    """The running process of the check registered as `key`, for its guard to `finish`,
    after starting every registered check not yet started. A check no guard takes is
    stopped when the run ends."""
    for name, start in list(_STARTERS.items()):
        _RUNNING[name] = start()
        del _STARTERS[name]
    return _RUNNING.pop(key)


@atexit.register
def _stop_unclaimed():
    for process in _RUNNING.values():
        process.kill()
        process.communicate()
    _RUNNING.clear()
