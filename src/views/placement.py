"""Keep a scripted window out of the owner's way (Windows only): on the monitor that does
not hold the owner's window, at the bottom of the z-order, and never activated or
focused. `--shot` and `tools/time_board.py` use it; the app run by hand does not.

    guard_foreground()           # before the window is built
    window, controller = build_app(...)
    keep_behind(window, controller.workspace)   # before the window is first shown

How:
- The owner's monitor is the one holding the centre of the owner's window, read from the
  owner's note when the Workspace names one (`owner_window_note`: a JSON file of the
  window's x, y, width and height, kept by some other tool; unset by default), else the
  window in front now, else the primary. The window goes to the top
  left of the first other monitor's work area (the same monitor when there is only one).
- WS_EX_NOACTIVATE on the frame, so Windows never activates it on show or click.
- The window's `deiconify` (which Tk follows with a raise and a forced focus, and which
  CustomTkinter calls on the first `update`, and again on every light/dark palette switch)
  becomes `wm state normal` (a show with no raise or focus), then a move to the bottom of
  the z-order. `lift` and `focus_force` do nothing on it.
- A guard thread, started before the window is built, watches the foreground. If any
  window of this process takes it anyway (Tk can, as it creates the window), the
  foreground goes straight back to the window that had it, and ours to the bottom.

PrintWindow (src/views/screenshot.py) draws a covered window, so stills still come out right.
"""

import ctypes
import json
import os
import sys
import threading
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from src.system import WINDOWS

# The Workspace setting naming the owner's note; absent by default, and then no note is read.
OWNER_NOTE_SETTING = "owner_window_note"
MARGIN = 5           # px from the monitor's work-area corner

_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000
_HWND_BOTTOM = 1
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOACTIVATE = 0x1, 0x2, 0x10
_EVENT_SYSTEM_FOREGROUND = 0x0003
_WM_QUIT = 0x0012


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _user32():
    return ctypes.windll.user32


def monitors():
    """Every monitor as (monitor rect, work-area rect, is primary), rects (l, t, r, b)."""
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def each(handle, _dc, _rect, _data):
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        _user32().GetMonitorInfoW(handle, ctypes.byref(info))
        m, w = info.rcMonitor, info.rcWork
        found.append(((m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom),
                      bool(info.dwFlags & 1)))
        return True
    _user32().EnumDisplayMonitors(None, None, proc(each), 0)
    return found


def owner_note(workspace):
    """The owner's note path the Workspace names, or None when it names none."""
    path = workspace.setting(OWNER_NOTE_SETTING, "")
    return Path(path) if path else None


def owner_point(note_path=None):
    """The centre of the owner's window: from the note at `note_path` (None: no note is
    read), else the window in front. A note that can't be read is said on stderr."""
    if note_path is not None:
        try:
            note = json.loads(Path(note_path).read_text(encoding="utf-8"))
            return (int(note["x"] + note["width"] / 2), int(note["y"] + note["height"] / 2))
        except (OSError, ValueError, KeyError, TypeError) as failed:
            print(f"wayfinder-board: can't read the owner's window note {note_path}: "
                  f"{type(failed).__name__}: {failed}", file=sys.stderr)
    front = _user32().GetForegroundWindow()
    rect = wintypes.RECT()
    if front and _user32().GetWindowRect(front, ctypes.byref(rect)):
        return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    return None


def away_work_area(all_monitors, point):
    """The work area of the first monitor that does not hold `point` (the owner's), else
    of the owner's own monitor when it is the only one. `point` None: the primary's."""
    if not all_monitors:
        return None
    home = None
    if point is not None:
        x, y = point
        home = next((i for i, (m, _w, _p) in enumerate(all_monitors)
                     if m[0] <= x < m[2] and m[1] <= y < m[3]), None)
    if home is None:
        home = next((i for i, (_m, _w, primary) in enumerate(all_monitors) if primary), 0)
    away = next((i for i in range(len(all_monitors)) if i != home), home)
    return all_monitors[away][1]


def keep_behind(window, workspace=None, move=True):
    """Place `window` (a Tk root not yet shown) away from the owner, behind everything,
    never active; the owner's note is the one `workspace` names, None for none. Nothing
    off Windows. `move=False` leaves it where it is: a menu's dropdown under its button
    (`--menu`), which goes behind and never active too."""
    if not WINDOWS:
        return
    user32 = _user32()
    window.update_idletasks()
    hwnd = user32.GetParent(window.winfo_id()) or int(window.wm_frame(), 16)
    user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) | _WS_EX_NOACTIVATE)
    area = None
    if move:
        note_path = owner_note(workspace) if workspace is not None else None
        area = away_work_area(monitors(), owner_point(note_path))
    if area is not None:
        tk.Wm.wm_geometry(window, f"+{area[0] + MARGIN}+{area[1] + MARGIN}")

    def to_bottom():
        user32.SetWindowPos(hwnd, _HWND_BOTTOM, 0, 0, 0, 0, _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)

    def show():
        tk.Wm.wm_state(window, "normal")
        to_bottom()

    window.deiconify = show
    window.wm_deiconify = show
    window.lift = window.tkraise = window.focus_force = lambda *_a, **_k: None
    guard_foreground()
    to_bottom()


_guard_thread = None


def guard_foreground():
    """Start (once) a thread that hands the foreground straight back to the window that had
    it whenever a window of this process takes it. Call it before the window is built:
    Tk can take the foreground as it creates the window, before `keep_behind` can run."""
    global _guard_thread
    if _guard_thread is not None or not WINDOWS:
        return
    user32 = _user32()
    user32.GetForegroundWindow.restype = wintypes.HWND
    me = os.getpid()

    def pid_of(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    front = user32.GetForegroundWindow()
    state = {"owner": front if front and pid_of(front) != me else None}
    hook_proc = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                   wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

    def on_foreground(_hook, _event, front, _obj, _child, _thread, _time):
        if not front:
            return
        if pid_of(front) == me:
            if state["owner"]:
                user32.SetForegroundWindow(state["owner"])
            user32.SetWindowPos(front, _HWND_BOTTOM, 0, 0, 0, 0,
                                _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)
        else:
            state["owner"] = front

    callback = hook_proc(on_foreground)
    ready = threading.Event()

    def run():
        hook = user32.SetWinEventHook(_EVENT_SYSTEM_FOREGROUND, _EVENT_SYSTEM_FOREGROUND, None,
                                      callback, 0, 0, 0)
        ready.set()
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
        user32.UnhookWinEvent(hook)
    _guard_thread = threading.Thread(target=run, daemon=True, name="keep-behind-guard")
    _guard_thread.callback = callback    # the ctypes callback lives as long as the thread
    _guard_thread.start()
    ready.wait(2)
