"""Keep every Tcl call on the UI thread.

The background runner's thread can run Python's garbage collection, and a collection
finalizes whatever garbage it finds: fonts, variables and images left by destroyed
widgets. Their finalizers call Tcl, and Tcl called from another thread stalls it (seen
in the timing harness: a scan stuck in `Font.__del__`). So, once installed:

    finalize_on_ui_thread()   # once, by the window
    run_pending()             # on the UI thread, from the window's timer

a font, variable or image finalized off the UI thread is kept, and its finalizer is
queued; `run_pending` runs the queue on the UI thread. On the UI thread a finalizer
runs at once, as before.
"""

import threading
import tkinter
import tkinter.font
from collections import deque

_pending = deque()   # finalizers waiting for the UI thread; deque appends are thread-safe
_installed = False


def _guard(original):
    def __del__(self):
        if threading.current_thread() is threading.main_thread():
            original(self)
        else:
            _pending.append(lambda: original(self))   # keeps self until the UI thread runs it
    __del__.__wrapped__ = original
    return __del__


def finalize_on_ui_thread():
    """Make the Tcl-calling finalizers of fonts, variables and images run on the UI
    thread only. Safe to call more than once."""
    global _installed
    if _installed:
        return
    for cls in (tkinter.font.Font, tkinter.Variable, tkinter.Image):
        cls.__del__ = _guard(cls.__del__)
    _installed = True


def run_pending():
    """On the UI thread: run every finalizer queued from another thread."""
    while _pending:
        finalizer = _pending.popleft()
        try:
            finalizer()
        except Exception:   # as a finalizer's error would be: ignored (the app may be closing)
            pass
