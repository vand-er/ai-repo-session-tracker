"""The Sessions tab: every recent Claude Code Session as a table (Title, Project, Last
message, By, Model, Ticket) under a one-line caption. It draws rows of text it is given and
reads no files. A poll only changes the text of the cells that changed.

The rows are drawn on one canvas (fast-live-board 04): as a grid of labels (six windows a
row, and the orchestrators' subagents are rows too) the tab took a tenth of a second to
repaint each time it came to the front. Each cell's text sits where its label put it: a
column is `char * width + 20` px (the label's 2 px border and 8 px padding each side), a
row as tall as the text plus 7 px above and below."""

import tkinter as tk

import customtkinter as ctk

from src.views.shapes import Items
from src.views.text_fit import cut

SIZE = "table_airy"
WIDTHS = (40, 18, 13, 10, 20, 40)   # in characters, one per column
LABEL_BD, PADX, PADY = 2, 8, 5       # a cell label's border and padding, in px
EMPTY = "No recent sessions."
EMPTY_PAD = 8                        # the "No recent sessions." label's padding
WHEEL_DIVISOR = 6                    # a wheel step scrolls delta / 6 px, as CTkScrollableFrame did


class SessionsView(tk.Frame):
    def __init__(self, parent, theme, headings):
        super().__init__(parent, bg=theme["bg"], highlightthickness=0, borderwidth=0)
        self.theme = theme
        self.headings = tuple(headings)
        self.rows = []           # the rows shown: tuples of cell text, cut to width
        self.selected = None     # the index of the highlighted row, None for none
        self._items = []         # per row: (background, [text item per column])
        self._region = None      # the body's scrollregion as last set
        self._thumb = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.caption = ctk.CTkLabel(self, text="", anchor="w")
        self.caption.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        self.header = tk.Frame(self)
        self.header.grid(row=1, column=0, sticky="ew")
        for c, heading in enumerate(self.headings):
            tk.Label(self.header, text=heading, anchor="w", width=WIDTHS[c], padx=8, pady=4
                     ).grid(row=0, column=c, sticky="ew")
        tk.Frame(self.header, width=16).grid(row=0, column=len(WIDTHS))
        self.table = tk.Frame(self, highlightthickness=0, borderwidth=0)
        self.table.grid(row=2, column=0, sticky="nsew")
        self.table.grid_rowconfigure(0, weight=1)
        self.table.grid_columnconfigure(0, weight=1)
        self.body = tk.Canvas(self.table, highlightthickness=0, borderwidth=0, yscrollincrement=1)
        self.body.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(self.table, command=self._scrolled)
        self.scrollbar.grid(row=0, column=1, sticky="nsew", padx=(0, 1))
        self.body.configure(yscrollcommand=self._view_moved)
        self.body.bind("<MouseWheel>", self._wheel)
        self.items = Items(self.body)
        self._empty = self.body.create_text(0, 0, anchor="nw", text=EMPTY, state="hidden")
        self.set_theme(theme)

    # ---------- called by the controller ----------
    def show(self, rows, caption, selected=None):
        """Draw `rows` (tuples of cell text, in heading order) under `caption`, the row at
        index `selected` highlighted and scrolled into view when it moves (09: a click on a
        Builder's Activity selects its row)."""
        if self.caption.cget("text") != caption:
            self.caption.configure(text=caption)
        self.rows = [tuple(cut(text, w) for text, w in zip(row, WIDTHS)) for row in rows]
        moved = selected != self.selected
        self.selected = selected
        self._draw()
        if moved and selected is not None:
            self.after_idle(self._reveal)

    def set_in_front(self, front):
        """Told by the window when this tab comes to the front or goes behind: the
        Sessions tab keeps nothing back while behind, so there is nothing to do."""

    def set_theme(self, theme):
        """Recolour in `theme`, in place, keeping the rows shown."""
        self.theme = t = theme
        self.char = t.char_width(SIZE)
        self._font = t.tk_mono(SIZE)
        self._row_h = t.point_font("mono", SIZE).metrics("linespace") + 2 * (PADY + LABEL_BD)
        self.configure(bg=t["bg"])
        self.caption.configure(text_color=t["text_muted"], font=t.mono("readout"),
                               bg_color=t["bg"])
        self.header.configure(bg=t["bg_raised"])
        for child in self.header.winfo_children():
            child.configure(bg=t["bg_raised"])
            if isinstance(child, tk.Label):
                child.configure(fg=t["text_muted"], font=t.tk_mono(SIZE, "bold"))
        self.table.configure(bg=t["bg_panel"])
        self.body.configure(bg=t["bg_panel"])
        self.scrollbar.configure(fg_color=t["bg_panel"], button_color=t["bg_raised"],
                                 button_hover_color=t["bg_select"])
        self._draw()

    # ---------- drawing ----------
    def _row_height(self):
        return self._row_h

    def _draw(self):
        """Lay out every row, touching only what changed."""
        t, rows = self.theme, self.rows
        row_h = self._row_height()
        widths = [self.char * w + 2 * (PADX + LABEL_BD) for w in WIDTHS]
        right = sum(widths)   # a row's labels ended at the last column
        while len(self._items) < len(rows):
            bg = self.body.create_rectangle(0, 0, 0, 0, width=0)
            texts = [self.body.create_text(0, 0, anchor="w") for _ in WIDTHS]
            self._items.append((bg, texts))
        for r, (bg, texts) in enumerate(self._items):
            if r >= len(rows):
                for item in (bg, *texts):
                    self.items.put(item, state="hidden")
                continue
            y = r * row_h
            fill = t["bg_select"] if r == self.selected else t["bg_panel"]
            self.items.put(bg, (0, y, right, y + row_h), state="normal", fill=fill)
            x = 0
            for c, (item, text) in enumerate(zip(texts, rows[r])):
                self.items.put(item, (x + LABEL_BD + PADX, y + row_h // 2), state="normal",
                          text=text, fill=self._fg(c, text), font=self._font)
                x += widths[c]
        self.items.put(self._empty, (LABEL_BD + EMPTY_PAD, LABEL_BD + EMPTY_PAD),
                  state="hidden" if rows else "normal", fill=t["text_muted"], font=self._font)
        region = (0, 0, right, len(rows) * row_h)
        if self._region != region:
            self._region = region
            self.body.configure(scrollregion=region)

    def _fg(self, column, text):
        """The Ticket column is drawn in the accent colour when a Session is on one."""
        on_ticket = column == len(WIDTHS) - 1 and text != "—"
        return self.theme["accent"] if on_ticket else self.theme["text"]

    def _reveal(self):
        """Scroll so the selected row is in view, a third of the way down, when it is not."""
        if self.selected is None or self.selected >= len(self.rows):
            return
        row_h, view = self._row_height(), self.body.winfo_height()
        total = len(self.rows) * row_h
        if view <= 1 or total <= view:
            return
        top, y = self.body.canvasy(0), self.selected * row_h
        if y < top or y + row_h > top + view:
            self.body.yview_moveto(max(0.0, (y - view / 3) / total))

    # ---------- scrolling ----------
    def _view_moved(self, first, last):
        """Move the scrollbar's thumb, only when it moves (it redraws on every set)."""
        if (first, last) != self._thumb:
            self._thumb = (first, last)
            self.scrollbar.set(first, last)

    def _scrolled(self, *args):
        self.body.yview(*args)

    def _wheel(self, event):
        if self.body.yview() != (0.0, 1.0):
            self.body.yview_scroll(-int(event.delta / WHEEL_DIVISOR), "units")
