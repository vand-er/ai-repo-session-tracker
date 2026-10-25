"""Protocol conformance: does a class satisfy one of the view Protocols in
`src/view_protocols.py`? Checks names and arity, which `runtime_checkable` does not.

- A method must be there, callable, and accept every call the Protocol's signature allows:
  each count of positional arguments from its required ones to all of them, and each
  keyword parameter (one after `/`) passed by name or left out.
- A settable callback (an annotation on the Protocol) must be on the class (an attribute
  or a property) or assigned to `self` in an `__init__` of the class or its bases.

Classes, not instances, are checked, so no window is ever built.
"""

import dis
import inspect

from tests.guards.tree import REPO, finish, start_python

REAL_VIEWS = (
    ("src.views.window", "MainWindow", "MainWindowProtocol"),
    ("src.views.board_view", "BoardView", "BoardViewProtocol"),
    ("src.views.sessions_view", "SessionsView", "SessionsViewProtocol"),
)
# What the conformance test itself imports: none of it may bring in a GUI toolkit.
GUARD_IMPORTS = ("src.view_protocols", "tests.fakes", "tests.guards.protocols")


def _methods(protocol):
    return {name: value for name, value in vars(protocol).items()
            if inspect.isfunction(value) and not name.startswith("_")}


def _callbacks(protocol):
    return list(vars(protocol).get("__annotations__", {}))


def _calls(signature):
    """`(args, kwargs)` for each call `signature` allows, `self` left out."""
    params = list(signature.parameters.values())[1:]
    positional = [p for p in params if p.kind is p.POSITIONAL_ONLY]
    by_name = [p.name for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    required = sum(1 for p in positional if p.default is p.empty)
    for count in range(required, len(positional) + 1):
        yield [None] * count, {}
    for name in by_name:
        yield [None] * required, {name: None}


def _assigned_in_init(cls, name):
    for klass in cls.__mro__:
        init = vars(klass).get("__init__")
        if inspect.isfunction(init) and any(
                ins.opname == "STORE_ATTR" and ins.argval == name
                for ins in dis.get_instructions(init)):
            return True
    return False


def protocol_gaps(cls, protocol):
    """One line for each way `cls` fails `protocol`, naming both and the member; [] if none."""
    gaps = []
    where = f"{cls.__name__} vs {protocol.__name__}"
    for name, wanted in _methods(protocol).items():
        found = getattr(cls, name, None)
        if not callable(found):
            gaps.append(f"{where}: lacks the method {name}")
            continue
        try:
            signature = inspect.signature(found)
        except (TypeError, ValueError):
            continue   # no signature to read (a builtin): its name is all we can check
        for args, kwargs in _calls(inspect.signature(wanted)):
            try:
                signature.bind(None, *args, **kwargs)
            except TypeError as err:
                shape = ", ".join([f"{len(args)} positional", *(f"{k}=" for k in kwargs)])
                gaps.append(f"{where}: {name}({shape}) does not bind on it: {err}")
                break
    for name in _callbacks(protocol):
        if not hasattr(cls, name) and not _assigned_in_init(cls, name):
            gaps.append(f"{where}: lacks the settable callback {name}")
    return gaps


_CHECK_REAL = """
import importlib
from tests.guards.protocols import GUARD_IMPORTS, REAL_VIEWS, protocol_gaps
from tests.guards.tree import TOOLKITS
for name in GUARD_IMPORTS:
    importlib.import_module(name)
toolkits = [t for t in TOOLKITS if t in sys.modules]
protocols = importlib.import_module("src.view_protocols")
gaps = []
for module, cls, protocol in REAL_VIEWS:
    gaps += protocol_gaps(getattr(importlib.import_module(module), cls),
                          getattr(protocols, protocol))
print(json.dumps({"toolkits": toolkits, "gaps": gaps}))
"""


def start_real_view_check(root=REPO):
    """Start the real-view check in a fresh interpreter, since importing a view imports a
    GUI toolkit; it builds no window. Give the result to `real_view_check`. Started apart
    so that it can run beside other guards: an interpreter's start is most of its cost."""
    return start_python(_CHECK_REAL, root)


def real_view_check(check=None):
    """The result of `check` (from `start_real_view_check`), or of a check started now:
    `{"gaps": protocol_gaps of each real view against its Protocol, "toolkits": the GUI
    toolkits the GUARD_IMPORTS brought in before any view was imported}`."""
    return finish(check or start_real_view_check(), "the real-view check")
