"""Scripted evidence: capture the window to a PNG, then call `done`. Windows only; uses
PowerShell's System.Drawing, so it needs no extra package.

The window paints itself into the PNG (PrintWindow), so another app's window lying on
top of ours cannot end up in the picture, and ours never needs to come to the front:
`--shot` keeps it behind every window, unfocused (src/views/placement.py). An open menu
is a window of its own (`--menu`): each one given in `also` paints itself too, and is
laid over the window's picture where it sits on screen."""

import ctypes
import subprocess
from ctypes import wintypes
from pathlib import Path

_PRINT_WINDOW = r'''
using System; using System.Drawing; using System.Runtime.InteropServices;
public static class WfbShot {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
  static Bitmap Paint(IntPtr h, out RECT r) {
    GetWindowRect(h, out r);
    var b = new Bitmap(r.R - r.L, r.B - r.T); var g = Graphics.FromImage(b);
    var dc = g.GetHdc(); PrintWindow(h, dc, 2); g.ReleaseHdc(dc); g.Dispose();
    return b;
  }
  public static void Shot(IntPtr h, IntPtr[] over, string path) {
    SetProcessDPIAware(); RECT r; var b = Paint(h, out r); var g = Graphics.FromImage(b);
    foreach (var o in over) {
      RECT s; var p = Paint(o, out s); g.DrawImage(p, s.L - r.L, s.T - r.T); p.Dispose();
    }
    b.Save(path, System.Drawing.Imaging.ImageFormat.Png); g.Dispose(); b.Dispose();
  }
}'''


def shoot(window, out_path, done, delay_ms=1500, also=None):
    """Wait `delay_ms` for `window` to draw, then save it to `out_path`. It is never raised
    or focused. `also()`, when given, lists the open popups (Tk toplevels) to lay over it."""
    window.update()
    window.after(delay_ms, lambda: _capture(window, out_path, done, also))


def _frame(widget):
    return int(widget.wm_frame(), 16)


def _window_rect(window):
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(wintypes.HWND(_frame(window)), ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def _capture(window, out_path, done, also=None, tries=5):
    window.update()
    x, y, w, h = _window_rect(window)
    if (x < -1000 or w < 600) and tries:  # minimised or not yet mapped: restore, retry
        window.state("normal")            # a show with no raise and no focus
        window.after(1000, lambda: _capture(window, out_path, done, also, tries - 1))
        return
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    over = ",".join(f"[IntPtr]{_frame(p)}" for p in (also() if also else []))
    script = (f"Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'\n{_PRINT_WINDOW}\n'@;"
              f"[WfbShot]::Shot([IntPtr]{_frame(window)}, [IntPtr[]]@({over}), '{out}')")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    print(f"saved {out} ({w}x{h} at {x},{y})")
    done()
