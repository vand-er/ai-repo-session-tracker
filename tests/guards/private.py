"""The toolkit-private rule, read from a tree's source: only the adapter module,
`src.views.ctk_internals`, touches customtkinter's internals, so a customtkinter upgrade
breaks in one place. It returns one line per violation, naming the module, the line and
what it found; an empty list means the rule holds.

It flags, in every view (the layer guard keeps the toolkit out of every module but the
views and the composition root, and the composition root only builds and wires them; its
`os._exit` is no toolkit reach):

- a read of an attribute starting with one `_` on anything other than `self` or `cls`, which
  is how a view reaches a toolkit object's private parts (`widget._canvas`). The app's own
  `self._x` is its own business. Dunders (`obj.__class__`) are public.

and in every app module:

- an import from a package inside customtkinter (`customtkinter.windows.widgets`); only
  the top-level `customtkinter` is public.

Tests and tools are not app modules, so they are exempt.
"""

import ast

from tests.guards.layers import VIEWS
from tests.guards.tree import app_modules, source, tree, within

ADAPTER = "src.views.ctk_internals"
TOOLKIT = "customtkinter"


def _private(attr):
    return attr.startswith("_") and not attr.startswith("__")


def _internal(module):
    return module.startswith(TOOLKIT + ".")


def private_violations(root):
    """One line per private toolkit reach outside the adapter, naming module and line."""
    found = []
    for name in app_modules(root):
        if name == ADAPTER:
            continue
        a_view = within(name, VIEWS)
        for node in ast.walk(tree(root).parse(source(root, name))):
            if a_view and isinstance(node, ast.Attribute) and _private(node.attr):
                if isinstance(node.value, ast.Name) and node.value.id in ("self", "cls"):
                    continue
                found.append(f"{name} line {node.lineno}: reads {ast.unparse(node)} "
                             f"(reach the toolkit's internals through {ADAPTER})")
            elif isinstance(node, ast.Import):
                found.extend(f"{name} line {node.lineno}: imports {alias.name} "
                             f"(only the top-level {TOOLKIT} is public)"
                             for alias in node.names if _internal(alias.name))
            elif isinstance(node, ast.ImportFrom) and not node.level \
                    and _internal(node.module or ""):
                found.append(f"{name} line {node.lineno}: imports from {node.module} "
                             f"(only the top-level {TOOLKIT} is public)")
    return found
