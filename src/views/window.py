"""The main window: options bar on top, tab strip under it, and the fronted tab's Board
filling the rest. One Board view per open tab is kept, stacked; only the fronted one is
shown. All layout is grid. The window reports user actions to `self.controller`.

Every stacked view (a Board, the Sessions tab) provides set_theme(theme) and
set_in_front(front), told when it comes to the front or goes behind."""

import ctypes
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from src.system import WINDOWS
from src.views.board_view import BoardView
from src.views.ctk_quiet import quiet_scrollbars
from src.views.options_bar import OptionsBar
from src.views.sessions_view import SessionsView
from src.views.tab_strip import TabStrip
from src.views.theme import Theme, appearance
from src.views.ui_thread import finalize_on_ui_thread, run_pending

TITLE = "Wayfinder board"
FINALIZE_MS = 250   # how often clean-up queued by the scan thread is run
RESTYLE_MS = 300    # after a theme switch, the views behind restyle one per this, when idle
EMPTY = "No tabs open.\nFile → New tab, or + New tab, to open a Source folder."


_DWMWA_USE_IMMERSIVE_DARK_MODE = (20, 19)   # the attribute, and its number before 20H1
_WM_NCACTIVATE = 0x0086


def set_title_bar(window, dark):
    """Make `window`'s title bar dark or light (Windows only), as CustomTkinter does, but
    without hiding and re-showing the window: the caption is repainted in place."""
    if not WINDOWS:
        return
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(window.winfo_id())
    value = ctypes.c_int(1 if dark else 0)
    for attribute in _DWMWA_USE_IMMERSIVE_DARK_MODE:
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
            break
    # Windows 10 draws the new colour at the caption's next paint: paint it now, ending in
    # the window's real active state, so focus and activation do not change.
    active = user32.GetForegroundWindow() == hwnd
    user32.SendMessageW(hwnd, _WM_NCACTIVATE, int(not active), 0)
    user32.SendMessageW(hwnd, _WM_NCACTIVATE, int(active), 0)


class MainWindow(ctk.CTk):
    def __init__(self, palette):
        ctk.set_appearance_mode(appearance(palette))   # before the window: its title bar
        super().__init__()
        self.controller = None
        self.boards = []
        self._front = None        # the view in front, or None
        self._stale = []          # views behind, not yet restyled since a theme switch
        self._restyle_id = None
        self.title(TITLE)
        self.geometry("1890x1000+5+5")
        self.minsize(1100, 700)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._fonts = {}          # every Theme's fonts, shared: see Theme
        self.theme = Theme(palette, self._fonts)

        self.options_bar = OptionsBar(self, self.theme)
        self.options_bar.grid(row=0, column=0, sticky="ew")
        self.tab_strip = TabStrip(self, self.theme,
                                  on_front=lambda i: self.controller.front(i),
                                  on_close=lambda i: self.controller.close_tab(i),
                                  on_new=lambda: self.controller.new_tab())
        self.tab_strip.grid(row=1, column=0, sticky="ew", padx=8, pady=(6, 0))
        # A plain Tk frame: a square CTkFrame looks the same, and its own canvas, under
        # every view, was redrawn whole on each theme switch.
        self.body = tk.Frame(self, highlightthickness=0, borderwidth=0)
        self.body.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(self.body, text=EMPTY, justify="center")
        self._empty_theme = None   # the theme the empty-window hint was last drawn in
        self._colour()
        self.protocol("WM_DELETE_WINDOW", lambda: self.controller.quit())
        finalize_on_ui_thread()   # the scan thread may garbage-collect fonts and images
        self.after(FINALIZE_MS, self._finalize)

    def _finalize(self):
        """Run the Tcl clean-up left by another thread's garbage collection (ui_thread.py)."""
        run_pending()
        self.after(FINALIZE_MS, self._finalize)

    # ---------- called by the controller ----------
    def set_theme(self, palette):
        """Restyle the whole window in `palette`, live: every part recolours what it has
        drawn, in place. Nothing is rebuilt."""
        mode = appearance(palette)
        if ctk.get_appearance_mode().lower() != mode:
            # A CustomTkinter internal, kept because there is no public way to change the
            # mode without ctk.set_appearance_mode, which redraws every widget of the
            # toolkit (tens of ms) and hides and re-shows the window to recolour its title
            # bar. Every colour drawn here is given outright, so only new widgets'
            # defaults and the title bar follow the mode, and set_title_bar does the bar.
            ctk.AppearanceModeTracker.appearance_mode = 0 if mode == "light" else 1
            set_title_bar(self, dark=mode == "dark")
        self.theme = Theme(palette, self._fonts)
        self._colour()
        self.options_bar.set_theme(self.theme)
        self.tab_strip.set_theme(self.theme)
        # The view in front is restyled now. Those behind it are restyled when fronted,
        # or one at a time once the window is idle, so a switch pays for one view only.
        self._stale = [view for view in self.boards if view is not self._front]
        if self._front is not None:
            self._front.set_theme(self.theme)
        self._schedule_restyle()

    def _schedule_restyle(self):
        if self._restyle_id is not None:
            self.after_cancel(self._restyle_id)
        self._restyle_id = self.after(RESTYLE_MS, self._restyle_one) if self._stale else None

    def _restyle_one(self):
        self._restyle_id = None
        if self._stale:
            self._stale.pop(0).set_theme(self.theme)
        self._schedule_restyle()

    def set_tabs(self, titles, active):
        self.tab_strip.set_tabs(titles, active)

    def add_board(self, tab):
        controller = self.controller
        board = BoardView(self.body, self.theme,
                          on_effort=lambda name: controller.select_effort(tab, name),
                          on_select=lambda path: controller.select_file(tab, path))
        return self._stack(board)

    def add_sessions_view(self, headings):
        """The Sessions tab's view. It is stacked with the Boards, so `front_board` and
        `remove_board` take it too."""
        return self._stack(SessionsView(self.body, self.theme, headings))

    def _stack(self, view):
        """Every view stays laid out in the one cell, under the fronted one: fronting raises
        a view that is already built and mapped (mapping one costs a window per widget)."""
        self.boards.append(view)
        quiet_scrollbars(view)
        view.set_in_front(False)
        view.grid(row=0, column=0, sticky="nsew")
        view.lower()
        return view

    def remove_board(self, board):
        self.boards.remove(board)
        if board in self._stale:
            self._stale.remove(board)
        if board is self._front:
            self._front = None
        board.destroy()

    def front_board(self, board):
        if board is not self._front:
            for view, front in ((self._front, False), (board, True)):
                if view is not None:
                    view.set_in_front(front)
        self._front = board
        if board is None:   # no tab in front: only the hint shows
            for view in self.boards:
                view.grid_remove()
            self._colour_empty()
            self.empty.grid(row=0, column=0)
            return
        if board in self._stale:   # behind at the last theme switch, not restyled yet
            self._stale.remove(board)
            board.set_theme(self.theme)
        self.empty.grid_remove()
        if not board.winfo_manager():
            for view in self.boards:
                view.grid()
        board.tkraise()

    def ask_folder(self):
        return filedialog.askdirectory(parent=self, mustexist=True,
                                       title="Open a Source folder") or None

    def close(self):
        if self._restyle_id is not None:
            self.after_cancel(self._restyle_id)
        self.destroy()

    def show_scans(self, text):
        """The builder's per-tab scan counter (07), after the title."""
        self.title(f"{TITLE}  |  {text}" if text else TITLE)

    # ---------- drawing ----------
    def _colour(self):
        t = self.theme
        self.configure(fg_color=t["bg"])
        self.body.configure(bg=t["bg"])
        if self.empty.winfo_ismapped():
            self._colour_empty()
        else:   # restyled when it shows: a CTkLabel redraws on every configure
            self._empty_theme = None

    def _colour_empty(self):
        t = self.theme
        if self._empty_theme is not t:
            self._empty_theme = t
            self.empty.configure(text_color=t["text_muted"], font=t.ui("detail_title"),
                                 bg_color=t["bg"])
