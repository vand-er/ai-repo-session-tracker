"""Stop CustomTkinter's scrollbars flushing the whole window on every redraw.

CTkScrollbar ends each redraw (a thumb move, a recolour) with `update_idletasks` on its
canvas, which runs every pending layout and redraw in the window there and then: a few ms
each time, and a theme switch redraws each scrollbar several times. Its redraw is drawn
with the rest of the window at the next idle anyway, so the flush is skipped.

    quiet_scrollbars(widget)     # every CTkScrollbar in widget, itself included
"""

import tkinter as tk

import customtkinter as ctk

from src.views.ctk_internals import silence_scrollbar_flush


def _no_flush():
    pass


def quiet_scrollbars(widget):
    if isinstance(widget, ctk.CTkScrollbar):
        # No public way: the flush is hard-coded in CTkScrollbar's private redraw.
        silence_scrollbar_flush(widget, _no_flush)
    for child in tk.Misc.winfo_children(widget):
        quiet_scrollbars(child)
