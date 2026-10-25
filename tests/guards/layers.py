"""The layer rules, read from a tree's source. Each returns one line per violation, naming
the offending module and what it imports; an empty list means the rule holds.

Modules are found by walking the app package, so a new module is checked without anyone
listing it. The only names kept here are the rules themselves:

- the model is `src.model`, the views are `src.views`;
- a controller is any app module outside the model and the views whose name is
  `controller` or ends in `_controller` (today the Board and Sessions controllers);
- the composition root (`COMPOSITION`) builds the window and wires the views to the
  controllers, so it alone may import views and, through them, the toolkit.
"""

import ast
import json
import sys

from tests.guards.tree import (APP, TOOLKITS, app_modules, finish, source, start_python,
                               tree, within)

MODEL = "src.model"
VIEWS = "src.views"
PLATFORM = "src.system"
COMPOSITION = ("src.app", "src.__main__")


def is_controller(name):
    leaf = name.rsplit(".", 1)[-1]
    return (not within(name, MODEL) and not within(name, VIEWS)
            and (leaf == "controller" or leaf.endswith("_controller")))


def controllers(root):
    """The modules the controller rule covers, found by name."""
    return [name for name in app_modules(root) if is_controller(name)]


def imports_of(root, name):
    """Every module `name` imports, anywhere in its source, by absolute dotted name. A
    `from package import x` on a package of the tree counts as importing `package.x`."""
    path = source(root, name)
    package = name if path.endswith("/__init__.py") else name.rpartition(".")[0]
    found = []
    for node in ast.walk(tree(root).parse(path)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")[:len(package.split(".")) - node.level + 1]
                base = ".".join(anchor + ([base] if base else []))
            if tree(root).is_dir(base.replace(".", "/")):
                found.extend(f"{base}.{alias.name}" for alias in node.names)
            else:
                found.append(base)
    return found


def model_violations(root):
    """Model modules import only model modules, the platform module and the standard
    library."""
    out = []
    for name in app_modules(root):
        if not within(name, MODEL):
            continue
        for imported in imports_of(root, name):
            top = imported.split(".")[0]
            allowed_app = within(imported, MODEL) or within(imported, PLATFORM)
            if (top == APP and not allowed_app) or (top != APP and top not in sys.stdlib_module_names):
                out.append(f"{name} imports {imported}: the model imports only the model, "
                           "the platform module and the standard library")
    return out


def platform_violations(root):
    """The platform module, the bottom layer, imports only the standard library."""
    out = []
    for name in app_modules(root):
        if not within(name, PLATFORM):
            continue
        for imported in imports_of(root, name):
            if imported.split(".")[0] not in sys.stdlib_module_names:
                out.append(f"{name} imports {imported}: the platform module imports only "
                           "the standard library")
    return out


_IMPORT_EACH = """\
import importlib
names = json.loads(sys.argv[1])
toolkits = set(json.loads(sys.argv[2]))
def loaded():
    return {m.split('.')[0] for m in sys.modules} & toolkits
found = []
for name in names:
    before = loaded()
    importlib.import_module(name)
    new = sorted(loaded() - before)
    if new:
        found.append([name, ', '.join(new)])
print(json.dumps(found))
"""


def start_toolkit_check(root):
    """Start the toolkit rule's check of `root` in a fresh interpreter, so no other
    test's imports can hide a leak; give the result to `toolkit_violations`. Started apart
    so that checks can run side by side: an interpreter's start is most of their cost."""
    names = [name for name in app_modules(root)
             if not within(name, VIEWS) and name not in COMPOSITION]
    return start_python(_IMPORT_EACH, root, json.dumps(names), json.dumps(TOOLKITS))


def toolkit_violations(root, check=None):
    """No module outside the views and the composition root imports a GUI toolkit, even
    through another module. Each module is imported in turn in one fresh interpreter, and a
    toolkit that first appears on importing it is blamed on it. `check` is the running
    check from `start_toolkit_check(root)`, if one was started."""
    found = finish(check or start_toolkit_check(root), "the toolkit check")
    return [f"{name} brings in {toolkit}: only the views import a GUI toolkit"
            for name, toolkit in found]


def controller_violations(root):
    """Controllers never import views."""
    return [f"{name} imports {imported}: a controller never imports a view"
            for name in controllers(root)
            for imported in imports_of(root, name) if within(imported, VIEWS)]
