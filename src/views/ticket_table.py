"""One Effort's Tickets as a table drawn on one canvas: a fixed header over a scrolling
body, with each Ticket's mark drawn as a rounded badge in its Family's colour (the
Status, or the Progress file's word when that is further along: `src/model/marks.py`).

Why a canvas (fast-live-board 02): the widget-per-cell table it replaces took seconds to
build and lay out on every Effort switch, sort or column toggle. Here rows are drawn
items, and only the rows in view are drawn: a small pool of row slots, row `i` always in
slot `i % len(slots)`, each slot reconfigured only where what it shows has changed. So
every interaction re-configures what is drawn and never destroys and rebuilds it: an
Effort switch redraws the content in place, re-showing the same rows changes nothing,
selecting recolours two rows, a sort reorders, a column toggle re-lays out, a wheel step
moves the view and fills the rows that came into it.

The look is the widget table's, measured from it: each column `char * width + 20` px wide
(a tk.Label's 2 px border and 8 px padding each side), the Status column at least
`char * width + 16` (its grid minsize) and wide enough for its widest badge, rows as tall
as the badge plus 5 px above and below. The badge is CTkLabel's rounded shape, 6 px in
from its cell, drawn as one cached image per size and colours (CTk's eight font circles
per badge were a third of the paint time); only its corner pixels differ. The header's
Status column is 4 px wider than the body's, as before, so the header from Blocked by
onwards sits 4 px right of its cells.

Where other tickets plug in:
- Flash: `redraw_rows` redraws only changed rows in place, `flash` paints rows in the
  palette's `flash` slot for FLASH_MS; a row's colour is flash over selection over panel.
- Session column: shown by default; `show_sessions(session_for)` re-marks the Session
  cells in place, with the Session's title as a tooltip.
- Activity column (07): `show_activity({path: text})` sets each row's Builder's Activity
  in place; a long one is cut in its words, keeping its age. Stalled (08) draws it in
  the palette's `stalled` colour instead of the accent. Clicking an Activity calls
  `on_activity(path)` instead of selecting the row (09).
- Sorting: `ordered(tickets, sort, session_for)` gives the row order through
  `src/model/sorting.py`; `set_sort` reorders, and a heading click calls `on_sort(column
  key)`. The controller owns the sort (it survives rescans), so a click does not re-sort
  by itself.
- Theme: `set_theme(theme)` recolours and re-lays out in place (for a live theme switch).
"""

import math
import time
import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk

from src.model.sorting import DEFAULT_SORT, sort_rows
from src.views.shapes import Items, Scale
from src.views.text_fit import cut, cut_activity
from src.views.theme import blend
from src.views.tooltip import Tooltip

FRONTIER_MARK = "▶ "
SORT_MARK = {False: " ▲", True: " ▼"}   # on the sorted heading: ascending, descending
SIZE = "table_airy"   # the owner-approved table size of the chosen layout
FLASH_MS = 2000       # how long a row whose Status changed shows the flash colour

# The widget table's geometry, in px: a cell's tk.Label border and padding, the header's
# padding, and the badge (CTkLabel: height 22 + PADY, corner 8, 6 px in from its cell).
LABEL_BD, PADX, PADY, HEAD_PADY = 2, 8, 5, 4
BADGE_HEIGHT, BADGE_CORNER, BADGE_LEFT = 22 + PADY, 8, 6
STATUS_MINSIZE = 16   # the Status column's grid minsize: char * width + this
# The Activity column keeps at least this many characters in view, the Title giving them
# up down to TITLE_MIN: the room the 10 px palettes always left it at 1906 px.
ACTIVITY_MIN, TITLE_MIN = 16, 24


@dataclass
class Column:
    key: str
    heading: str
    width: int          # in characters
    visible: bool = True


def default_columns():
    return [
        Column("num", "#", 5),
        Column("title", "Title", 44),
        Column("type", "Type", 10),
        Column("status", "Status", 16),
        Column("blocked_by", "Blocked by", 16),
        Column("flag", "Flag", 9),
        Column("area", "Area", 16, visible=False),
        Column("updated", "Updated", 12),
        Column("session", "Session", 8),
        Column("activity", "Activity", 30),
    ]


def cell_text(tracked, key, width, session_for=None, activity=None):
    """The text of one cell, cut to `width` characters with an ellipsis. `activity` maps
    a Ticket path to its Builder's ActivityText; cut, it keeps its age."""
    t = tracked.ticket
    if key == "activity":
        return cut_activity((activity or {}).get(t.path), width)
    if key == "num":
        value = (FRONTIER_MARK if tracked.frontier else "  ") + t.number
    elif key == "title":
        value = t.title or t.path.name
    elif key == "blocked_by":
        value = ", ".join(t.blockers) or "—"
    elif key == "flag":
        value = "frontier" if tracked.frontier else ("blocked" if tracked.blocked else "")
    elif key == "updated":
        value = time.strftime("%m-%d %H:%M", time.localtime(t.mtime)) if t.mtime else "—"
    elif key == "session":
        value = (session_for(t.path) if session_for else None) and "●" or "—"
    else:
        value = getattr(t, key, "") or "—"
    return cut(value, width)


_STANDARD_WIDE = str.maketrans("", "", "—…")   # drawn at the standard width: see _join


def _plain(text):
    """Whether every character of `text` takes the monospaced font's standard width:
    ASCII, and the dash and ellipsis the cells use. Another (a curly quote, an arrow)
    may come from a fallback font of another width."""
    return text.translate(_STANDARD_WIDE).isascii()


def ordered(tickets, sort=DEFAULT_SORT, session_for=None):
    """Rows in display order: `sort` is (column key, descending); default Ticket number.
    `session_for` orders the Session column."""
    return sort_rows(tickets, *sort, session_for=session_for)


def badge_pixels(w, h, r, colour, bg, samples=4):
    """A rounded rectangle `w` x `h` with corner radius `r`, in `colour` on `bg`, as Tk
    photo data: the shape CTkLabel draws (corner circles centred `r` in from each edge),
    each corner pixel shaded by how much of it the circle covers."""
    def coverage(x, y):
        cx = r if x < r else (w - r if x >= w - r else None)
        cy = r if y < r else (h - r if y >= h - r else None)
        if cx is None or cy is None:
            return 1.0
        inside = sum((x + (i + 0.5) / samples - cx) ** 2 + (y + (j + 0.5) / samples - cy) ** 2
                     <= r * r for i in range(samples) for j in range(samples))
        return inside / samples ** 2

    shades = {}

    def shade(c):
        if c not in shades:
            shades[c] = blend(bg, colour, c)
        return shades[c]
    return " ".join("{" + " ".join(shade(coverage(x, y)) for x in range(w)) + "}"
                    for y in range(h))


class _Slot:
    """The drawn items of one row on screen."""

    def __init__(self, tag, bg, texts, badge, badge_text):
        self.tag = tag
        self.bg = bg                  # the row's background rectangle
        self.texts = texts            # column key -> text item (every column but Status)
        self.badge = badge            # the badge's shape, an image item
        self.badge_text = badge_text
        self.drawn = None             # what it shows now: see TicketTable._signature


class TicketTable(tk.Frame):
    """A plain Tk frame: as a square CTkFrame it looked the same, and its own canvas, lying
    under the header and body, was redrawn whole on every restyle."""

    def __init__(self, parent, theme, on_select):
        super().__init__(parent, bg=theme["bg_panel"], highlightthickness=0, borderwidth=0)
        self.on_select = on_select
        self.on_sort = None     # called with a column key when its heading is clicked
        self.on_activity = None  # called with a Ticket path when its Activity is clicked
        self.sort = DEFAULT_SORT
        self.columns = default_columns()
        self.session_for = None
        self.activity = {}      # Ticket path -> its Builder's Activity text
        self.stalled = frozenset()   # Ticket paths whose Builder is Stalled
        self.tickets = ()
        self.selected = None
        self.flashing = {}      # Ticket path -> token of its running flash
        self._rows = []         # TrackedTickets in display order
        self._index = {}        # Ticket path -> its row in `_rows`
        self._slots = []
        self._badge_images = {} # (w, h, colour, bg) -> the badge's shape: see _badge_image
        self._version = 0       # bumped when the layout or theme changes every row
        self._reveal_pending = False
        self._width = 1
        self._region = None     # the body's scrollregion as last set
        self._status_room = 0   # px the widest badge needs in the Status column
        self._inset = 0         # px at the bottom covered by another widget: see set_inset
        self.row_h = 1          # set by set_theme; the canvas may report its view before
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.header = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.body = ctk.CTkCanvas(self, highlightthickness=0, borderwidth=0, width=200,
                                  height=200, yscrollincrement=1)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.items = Items(self.body)
        self.px = Scale(self)
        self.scrollbar = ctk.CTkScrollbar(self, command=self._scrollbar_moved)
        self.scrollbar.grid(row=1, column=1, sticky="nsew", padx=(0, 1))
        self._thumb = None      # the scrollbar's (first, last) as last set
        self.body.configure(yscrollcommand=self._view_moved)
        self._headings = {c.key: self.header.create_text(0, 0, anchor="w", state="hidden")
                          for c in self.columns}
        self.tooltip = None
        self._tip_path = None
        self.header.bind("<Button-1>", self._header_clicked)
        self.header.bind("<Motion>", self._header_motion)
        self.body.bind("<Button-1>", self._body_clicked)
        self.body.bind("<MouseWheel>", self._wheel)
        self.body.bind("<Motion>", self._body_motion)
        self.body.bind("<Leave>", lambda _e: self._hide_tip())
        self.body.bind("<Configure>", self._resized)
        self.set_theme(theme)

    # ---------- public ----------
    def show(self, tickets, selected=None):
        """Draw these TrackedTickets, highlighting the one at path `selected`, from the
        first row, or with the selected row in view."""
        self.tickets = tuple(tickets)
        self.selected = selected
        self._reorder()
        self._scroll_top(0)
        self._fill()
        if self.selected in self._index:
            self.reveal_selected()

    def set_visible(self, key, visible):
        changed = False
        for column in self.columns:
            if column.key == key and column.visible != visible:
                column.visible, changed = visible, True
        if changed:
            self._relayout()
            self.show(self.tickets, self.selected)

    def show_sessions(self, session_for):
        """Mark each row whose Ticket a recent Session is on. `session_for(path)` gives that
        Session's title or None. Changes the Session cells in place; redraws nothing else,
        unless the table is sorted by the Session column and the marks change the row order."""
        self.session_for = session_for
        if self.sort[0] == "session" and self._order() != [t.ticket.path for t in self._rows]:
            self.redraw(self.tickets, self.selected)
            return
        self._fill()

    def show_activity(self, activity, stalled=frozenset()):
        """Show each row's Builder's Activity: `activity` maps a Ticket path to its text
        ("Editing shell.gd · 4s"); a row not in it shows none. A path in `stalled` shows
        it in the palette's `stalled` colour (08). Changes those cells in place."""
        self.activity = dict(activity)
        self.stalled = frozenset(stalled)
        self._fill()

    def set_inset(self, px):
        """The bottom `px` of the table is covered by another widget (the Board's detail
        pane, laid over it): rows are drawn, scrolled and revealed above it, and the
        scrollbar stops there. Showing or hiding the pane then moves no widget but the
        scrollbar, where resizing the table took tens of ms."""
        if px == self._inset:
            return
        self._inset = px
        self.scrollbar.grid_configure(pady=(0, px))
        self._set_scrollregion()
        self._fill()

    def set_theme(self, theme):
        """Draw in `theme` from now on: recolour and re-lay out what is shown, in place."""
        self.theme = t = theme
        self.configure(bg=t["bg_panel"])
        self.header.configure(bg=t["bg_raised"])
        self.body.configure(bg=t["bg_panel"])
        self.scrollbar.configure(bg_color=t["bg_panel"], fg_color=t["bg_panel"],
                                 button_color=t["bg_raised"],
                                 button_hover_color=t["bg_select"])
        self.char = t.char_width(SIZE)
        scale = self.px.factor
        self._font = t.point_font("mono", SIZE)
        self._font_bold = t.point_font("mono", SIZE, "bold")
        font_badge = t.font("mono", SIZE, "bold", scale=scale)   # as a CTkLabel scales it
        if font_badge is not getattr(self, "_font_badge", None):
            self._font_badge = font_badge
            self._badge_widths = {}
        # The gap between two columns' text in characters, when it is whole ones and the
        # font draws the dash and ellipsis cells use at its standard width: neighbouring
        # cells may then be drawn as one text (see _runs). 0 when they may not.
        gap = 2 * (PADX + LABEL_BD)
        self._join = (gap // self.char if gap % self.char == 0
                      and all(self._font.measure(c) == self.char for c in "0—…") else 0)
        line = self._font.metrics("linespace")
        label_h = line + 2 * (PADY + LABEL_BD)
        self._badge_h = round(BADGE_HEIGHT * scale)
        self._badge_pady = round(PADY * scale)
        self._badge_left = round(BADGE_LEFT * scale)
        self._radius = round(BADGE_CORNER * scale)
        self.row_h = max(label_h, self._badge_h + 2 * self._badge_pady)
        self._text_y = (self.row_h - label_h) // 2 + LABEL_BD + PADY + line // 2
        badge_line = self._font_badge.metrics("linespace")
        # The badge sat at the top of its cell's frame (a grid's default anchor is nw), so a
        # row made taller by its text (Cascadia Mono) leaves the badge high, not centred.
        self._badge_y = self._badge_pady
        self._badge_text_y = self._badge_y + (self._badge_h - badge_line) // 2 + badge_line // 2
        head_line = self._font_bold.metrics("linespace")
        self.header.configure(height=head_line + 2 * (HEAD_PADY + LABEL_BD))
        self._head_y = LABEL_BD + HEAD_PADY + head_line // 2
        if self.tooltip is not None:
            self.tooltip.hide()
        self.tooltip = Tooltip(self, t)
        # Every slot redraws (the layout version moves), reusing its items.
        self._status_room = 0
        self._relayout()
        self._reorder()
        self._fill()

    # ---------- live updates ----------
    def redraw(self, tickets, selected=None):
        """`show`, but keeping the scroll position: for a poll that found rows come or go."""
        top = self.body.canvasy(0)
        self.tickets = tuple(tickets)
        self.selected = selected
        self._reorder()
        self._scroll_top(top)
        self._fill()

    def redraw_rows(self, tickets, paths):
        """Take the new TrackedTickets and redraw only the rows at `paths`, in place. If
        the new rows would sort differently, redraw the table instead."""
        old = [t.ticket.path for t in self._rows]
        self.tickets = tuple(tickets)
        if self._order() != old:
            self.redraw(self.tickets, self.selected)
            return
        self._reorder()
        self._fill()

    def flash(self, paths, ms=FLASH_MS):
        """Paint the rows at `paths` in the palette's flash colour for `ms`."""
        for path in paths:
            token = self.flashing[path] = object()
            self.after(ms, lambda p=path, k=token: self._unflash(p, k))
        if paths:
            self._fill()

    def _unflash(self, path, token):
        if self.flashing.get(path) is token:
            del self.flashing[path]
            self._fill()

    def set_sort(self, column, descending):
        """Order rows by `column` (reversed when `descending`) and mark its heading."""
        if (column, descending) == self.sort:
            return
        self.sort = (column, descending)
        self._draw_header()
        self.show(self.tickets, self.selected)

    def select(self, path):
        self.selected = path
        self._fill()

    def reveal_selected(self):
        """Scroll the selected row into view: a third of the way down when it was above or
        below the view. Nothing when it is already in view."""
        index = self._index.get(self.selected)
        if index is None:
            return
        if self.body.winfo_height() <= 1:   # not laid out yet: reveal once it is
            self._reveal_pending = True
            return
        view = self._view_height()
        total = len(self._rows) * self.row_h
        if total <= view:
            return
        y, top = index * self.row_h, self.body.canvasy(0)
        if y < top or y + self.row_h > top + view:
            self._scroll_top(max(0, y - view / 3))
            self._fill()

    # ---------- layout ----------
    def _order(self):
        """The Ticket paths in the order the rows should be drawn now."""
        return [t.ticket.path for t in ordered(self.tickets, self.sort, self.session_for)]

    def _visible(self):
        return [c for c in self.columns if c.visible]

    def _reorder(self):
        """Put the rows in display order and size the scrolling area for them. The Status
        column widens if a badge needs it, as a grid column did."""
        self._rows = ordered(self.tickets, self.sort, self.session_for)
        self._index = {t.ticket.path: i for i, t in enumerate(self._rows)}
        room = max((self._badge_left + self._badge_width(t.mark_word or "?")[0]
                    for t in self._rows), default=0)
        if room > self._status_room:
            self._status_room = room
            self._relayout()
        self._set_scrollregion()

    def _set_scrollregion(self):
        """Size the scrolling area to the rows; only when it changes, as configuring the
        canvas repaints all of it."""
        region = (0, 0, self._width, len(self._rows) * self.row_h + self._inset)
        if region != self._region:
            self._region = region
            self.body.configure(scrollregion=region)

    def _relayout(self):
        """Work out each visible column's x in the header and the body, and draw the header."""
        self._chars, self._head_x, self._body_x = self._fit_columns()
        self._version += 1
        self._draw_header()

    def _fit_columns(self):
        """`(chars, head x, body x)`: each visible column's width in characters, its
        (key, x0, x1) in the header and its x in the body. A column is its own width,
        except that the Title gives up characters (down to TITLE_MIN) so the Activity
        column, last, keeps ACTIVITY_MIN in view: the wider fonts (frost, onyx, plum)
        left it no room at the owner's 1906 px."""
        chars = {c.key: c.width for c in self._visible()}
        head, body = self._place(chars)
        if "activity" in body and "title" in chars and self._width > 1:
            room = (self._width - body["activity"] - 2 * (PADX + LABEL_BD)) // max(1, self.char)
            if room < ACTIVITY_MIN:
                chars["title"] = max(TITLE_MIN, chars["title"] - (ACTIVITY_MIN - room))
                head, body = self._place(chars)
        return chars, head, body

    def _place(self, chars):
        head, body = [], {}
        hx = bx = 0
        for key, n in chars.items():
            width = self.char * n + 2 * (PADX + LABEL_BD)
            body_width = width
            if key == "status":
                body_width = max(self.char * n + STATUS_MINSIZE, self._status_room)
            head.append((key, hx, hx + width))
            body[key] = bx
            hx += width
            bx += body_width
        return head, body

    def _draw_header(self):
        t = self.theme
        shown = {key: x for key, x, _ in self._head_x}
        for column in self.columns:
            item = self._headings[column.key]
            if column.key not in shown:
                self.header.itemconfigure(item, state="hidden")
                continue
            sorted_here = column.key == self.sort[0]
            self.header.coords(item, shown[column.key] + LABEL_BD + PADX, self._head_y)
            self.header.itemconfigure(
                item, state="normal", font=self._font_bold,
                text=column.heading + (SORT_MARK[self.sort[1]] if sorted_here else ""),
                fill=t["text"] if sorted_here else t["text_muted"])

    def _badge_width(self, text):
        """(drawn width, text width) of a badge showing `text`: the text plus the
        CTkLabel's padding of one corner radius each side, floored to even as CTk draws it."""
        found = self._badge_widths.get(text)
        if found is None:
            text_w = self._font_badge.measure(text)
            pad = min(self._radius, round(self._badge_h / 2))
            found = self._badge_widths[text] = ((text_w + 2 * pad) // 2 * 2, pad)
        return found

    # ---------- drawing ----------
    def _scroll_top(self, y):
        total = len(self._rows) * self.row_h + self._inset
        if int(self.body.canvasy(0)) != int(y):     # a no-op move still repaints
            self.body.yview_moveto(y / total if total else 0)

    def _view_height(self):
        """The body's height that shows: all of it less what `set_inset` says is covered."""
        return max(self.body.winfo_height() - self._inset, 1)

    def _fill(self):
        """Make the rows in view show what they should: each slot is reconfigured only
        where its row, colour or content has changed. Slots out of view are hidden."""
        height = self._view_height()
        needed = math.ceil(max(height, 1) / self.row_h) + 1
        while len(self._slots) < needed:
            self._slots.append(self._new_slot(len(self._slots)))
        count = len(self._slots)
        top = int(self.body.canvasy(0))
        first = top // self.row_h
        last = min(len(self._rows), (top + max(height, 1)) // self.row_h + 1)
        used = set()
        for index in range(first, last):
            slot = self._slots[index % count]
            used.add(slot)
            self._draw_row(slot, index)
        for slot in self._slots:
            if slot not in used and slot.drawn is not None:
                for item in self._slot_items(slot):
                    self.items.put(item, state="hidden")
                slot.drawn = None
        self._view_moved()

    def _new_slot(self, n):
        body, tag = self.body, f"slot{n}"
        bg = body.create_rectangle(0, 0, 0, 0, width=0, tags=tag, state="hidden")
        texts = {c.key: body.create_text(0, 0, anchor="w", tags=tag, state="hidden")
                 for c in self.columns if c.key != "status"}
        badge = body.create_image(0, 0, anchor="nw", tags=tag, state="hidden")
        badge_text = body.create_text(0, 0, anchor="w", tags=tag, state="hidden")
        slot = _Slot(tag, bg, texts, badge, badge_text)
        for item in self._slot_items(slot):
            self.items.add(item, state="hidden")
        return slot

    @staticmethod
    def _slot_items(slot):
        return [slot.bg, *slot.texts.values(), slot.badge, slot.badge_text]

    def _badge_image(self, w, h, colour, bg):
        """The badge's rounded shape, `w` x `h` in `colour` on `bg`, as an image: one item
        to draw instead of CTk's two rectangles and eight font circles (a third of the
        table's paint time). Made once per size and colours."""
        key = (w, h, colour, bg)
        image = self._badge_images.get(key)
        if image is None:
            # CTk's font circles fill about a pixel inside their nominal radius: one less
            # matches today's corners best (fitted to the before shots).
            r = max(1, min(self._radius, w // 2, h // 2) - 1)
            image = self._badge_images[key] = tk.PhotoImage(master=self, width=w, height=h)
            image.put(badge_pixels(w, h, r, colour, bg))
        return image

    def _row_colour(self, path):
        if path in self.flashing:
            return self.theme["flash"]
        return self.theme["bg_select"] if path == self.selected else self.theme["bg_panel"]

    def _session_text(self, tracked):
        column = next(c for c in self.columns if c.key == "session")
        return cell_text(tracked, "session", column.width, self.session_for)

    def _draw_row(self, slot, index):
        tracked = self._rows[index]
        path = tracked.ticket.path
        drawn = (index, tracked, self._row_colour(path), self._session_text(tracked),
                 self._version, self._width, self.activity.get(path), path in self.stalled)
        if slot.drawn == drawn:
            return
        slot.drawn = drawn
        t, put, y = self.theme, self.items.put, index * self.row_h
        ticket = tracked.ticket
        fg = t["text_dim"] if tracked.blocked else t["text"]
        put(slot.bg, (0, y, self._width, y + self.row_h), state="normal", fill=drawn[2])
        cells = []    # (key, item, x, text, colour, font) per text cell shown, in order
        for column in self.columns:
            if column.key == "status":
                cells.append(None)   # the badge: no text run crosses it
                continue
            item = slot.texts[column.key]
            x = self._body_x.get(column.key)
            if x is None:
                put(item, state="hidden")
                continue
            colour = t["accent"] if tracked.frontier and column.key in ("num", "flag") else fg
            font = self._font_bold if column.key == "num" and tracked.frontier else self._font
            if column.key == "session":
                text = drawn[3]
                colour = t["accent"] if self.session_for and self.session_for(path) else t["text_dim"]
            elif column.key == "activity":
                # The last column: cut to the room left in the canvas, not past its edge.
                room = (self._width - x - 2 * (PADX + LABEL_BD)) // max(1, self.char)
                text = cell_text(tracked, "activity", max(8, min(column.width, room)),
                                 activity=self.activity)
                colour = t["stalled"] if drawn[7] else t["accent"]
            else:
                text = cell_text(tracked, column.key, self._chars[column.key], self.session_for)
            cells.append((column.key, item, x, text, colour, font))
        for run in self._runs(cells):
            key, item, x, _text, colour, font = run[0]
            put(item, (x + LABEL_BD + PADX, y + self._text_y), state="normal",
                text=self._joined(run), fill=colour, font=font)
            for cell in run[1:]:
                put(cell[1], state="hidden")
        self._draw_badge(slot, y, tracked, drawn[2])

    def _runs(self, cells):
        """The row's text cells in runs drawn as one text item each, at the very pixels
        the cells would have. A canvas paints each text item at a fixed cost (about 25 us
        here, whatever its length), so a row of nine cells drawn as four or five paints
        in half the time: on every Effort switch, theme switch and fronting of a Board.
        Cells join a run when they are neighbours of one colour and font, the column gap
        is whole characters of the monospaced font (`_join`), and every cell but the
        last is text of the font's standard width (`_plain`)."""
        runs = []
        for cell in cells:
            last = runs[-1][-1] if runs and runs[-1] and cell is not None else None
            if (last is not None and self._join and (cell[4], cell[5]) == (last[4], last[5])
                    and _plain(last[3])):
                runs[-1].append(cell)
            elif cell is not None:
                runs.append([cell])
            else:
                runs.append([])    # the badge ends the run before it
        return [run for run in runs if run]

    def _joined(self, run):
        """A run's cells as one text: each but the last padded to its column's width and
        the gap, in characters."""
        return "".join(text.ljust(self._chars[key] + self._join) for key, _, _, text, _, _
                       in run[:-1]) + run[-1][3]

    def _draw_badge(self, slot, y, tracked, bg):
        put = self.items.put
        x = self._body_x.get("status")
        if x is None:
            put(slot.badge, state="hidden")
            put(slot.badge_text, state="hidden")
            return
        t = self.theme
        text = tracked.mark_word or "?"   # the Status, or the record further along
        colour = t.family(tracked.mark)
        if tracked.blocked:
            colour = blend(colour, t["bg_panel"], 0.55)
        w, pad = self._badge_width(text)
        x0, y0 = x + self._badge_left, y + self._badge_y
        put(slot.badge, (x0, y0), state="normal",
            image=self._badge_image(w, self._badge_h // 2 * 2, colour, bg))
        put(slot.badge_text, (x0 + pad, y + self._badge_text_y), state="normal", text=text,
            fill=t["badge_text"], font=self._font_badge)

    # ---------- events ----------
    def _resized(self, event):
        if event.width != self._width:
            self._width = event.width
            self._set_scrollregion()
            if self._fit_columns()[0] != self._chars:   # the Title gives the Activity room
                self._relayout()
        self._fill()
        if self._reveal_pending and event.height > 1:
            self._reveal_pending = False
            self.reveal_selected()

    def _view_moved(self, *_fractions):
        """The canvas's view moved: move the scrollbar's thumb, only when it moves (the
        scrollbar redraws its rounded shape on every set, a few ms each). The thumb
        measures the rows against the part of the view not covered (`set_inset`)."""
        rows_h, view = len(self._rows) * self.row_h, self._view_height()
        if rows_h <= view:
            thumb = (0.0, 1.0)
        else:
            top = self.body.canvasy(0)
            thumb = (top / rows_h, min(1.0, (top + view) / rows_h))
        if thumb != self._thumb:
            self._thumb = thumb
            self.scrollbar.set(*thumb)

    def _scrollbar_moved(self, *args):
        if args and args[0] == "moveto":   # a fraction of the rows: see _view_moved
            rows_h = len(self._rows) * self.row_h
            self._scroll_top(max(0.0, float(args[1])) * rows_h)
        else:
            self.body.yview(*args)
        self._fill()

    def _wheel(self, event):
        """A wheel step scrolls as CTkScrollableFrame did on Windows: delta / 6 px."""
        if self.body.yview() == (0.0, 1.0):
            return
        self._hide_tip()
        self.body.yview_scroll(-int(event.delta / 6), "units")
        self._fill()

    def _row_at(self, event):
        index = int(self.body.canvasy(event.y)) // self.row_h
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _on_activity(self, event, tracked):
        """Whether `event` is on `tracked`'s Activity cell, and it shows an Activity."""
        x = self._body_x.get("activity")
        return (tracked is not None and x is not None and event.x >= x
                and bool(self.activity.get(tracked.ticket.path)))

    def _body_clicked(self, event):
        tracked = self._row_at(event)
        if tracked is None:
            return
        if self.on_activity is not None and self._on_activity(event, tracked):
            self.on_activity(tracked.ticket.path)   # opens its Builder's Session (09)
        else:
            self._clicked(tracked.ticket.path)

    def _body_motion(self, event):
        """The Session cell's tooltip: the Session's title, while the pointer is on it.
        The hand cursor over an Activity, which opens its Builder's Session."""
        tracked = self._row_at(event)
        cursor = "hand2" if self.on_activity is not None and self._on_activity(event, tracked) else ""
        if self.body.cget("cursor") != cursor:
            self.body.configure(cursor=cursor)
        x = self._body_x.get("session")
        column = next(c for c in self.columns if c.key == "session")
        over = (tracked is not None and x is not None
                and x <= event.x < x + self.char * column.width + 2 * (PADX + LABEL_BD))
        path = tracked.ticket.path if over else None
        if path == self._tip_path:
            return
        self._hide_tip()
        self._tip_path = path
        if path is not None and self.session_for:
            self.tooltip.show(self.session_for(path), event.x_root, event.y_root)

    def _hide_tip(self):
        self._tip_path = None
        if self.tooltip is not None:
            self.tooltip.hide()

    def _heading_at(self, x):
        return next((key for key, x0, x1 in self._head_x if x0 <= x < x1), None)

    def _header_motion(self, event):
        cursor = "hand2" if self._heading_at(event.x) else ""
        if self.header.cget("cursor") != cursor:
            self.header.configure(cursor=cursor)

    def _header_clicked(self, event):
        key = self._heading_at(event.x)
        if key is not None:
            self._heading_clicked(key)

    def _heading_clicked(self, key):
        if self.on_sort is not None:
            self.on_sort(key)

    def _clicked(self, path):
        self.select(path)
        self.on_select(path)
