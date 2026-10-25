"""A hover tooltip drawn from the palette. `attach_tooltip` gives one to a widget, asking
for its text at hover time, so a widget whose meaning changes between polls needs no
rebinding; `Tooltip` is the same window shown and hidden by hand, for a part of a widget
(a cell of the canvas Ticket table)."""

import tkinter as tk


class Tooltip:
    """One tooltip window beside the pointer, at most one shown at a time."""

    def __init__(self, widget, theme):
        self.widget, self.theme = widget, theme
        self.window = None

    def show(self, text, x_root, y_root):
        """Show `text` below-right of the pointer at (`x_root`, `y_root`), pulled left so
        it stays inside the app window. Nothing when `text` is None or ""."""
        self.hide()
        if not text:
            return
        theme = self.theme
        window = tk.Toplevel(self.widget)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        tk.Label(window, text=text, bg=theme["bg_raised"], fg=theme["text"],
                 font=theme.tk_mono("readout"), padx=8, pady=4, relief="solid", borderwidth=1,
                 highlightthickness=0).grid(row=0, column=0)
        window.update_idletasks()
        top = self.widget.winfo_toplevel()
        right = top.winfo_rootx() + top.winfo_width() - 8
        x = min(x_root + 12, right - window.winfo_reqwidth())
        window.geometry(f"+{max(x, 0)}+{y_root + 14}")
        self.window = window

    def hide(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None


def attach_tooltip(widget, theme, text_for):
    """Show `text_for()` beside the pointer while it is over `widget`; nothing when it
    gives None or ""."""
    tip = Tooltip(widget, theme)
    widget.bind("<Enter>", lambda e: tip.show(text_for(), e.x_root, e.y_root), add="+")
    widget.bind("<Leave>", lambda _e: tip.hide(), add="+")
    widget.bind("<Destroy>", lambda _e: tip.hide(), add="+")
    return tip
