"""The left sidebar of a Board: the Effort list (repo-root tabs only) and, beneath it, the
shown Effort's header as a tall card: title, Map or Spec Status, the stale-spec warning,
one line per Family with its count, and the done-share bar.

08 plugs in at `on_head`: clicking the card's title selects the Map or Spec."""

import customtkinter as ctk

from src.model.effort import BUILD, RESOLVED, WAYFINDER
from src.model.ticket import DONE, NEEDS_ME
from src.views.shapes import Items, Scale, Shapes

KIND_LABEL = {WAYFINDER: "map", BUILD: "spec", "": "folder"}
STALE_WARNING = "⚠ spec not done, every ticket is"


def done_share(effort):
    """(closed, total): Tickets Done or Dropped, and all Tickets."""
    return sum(effort.counts.get(f, 0) for f in RESOLVED), len(effort.tickets)


# The sidebar is drawn on one canvas (fast-live-board 04): it was a CustomTkinter frame of
# about ninety windows, rebuilt on every Effort switch (a third of a second) and slow to
# repaint whenever its tab came to the front. Every item is placed where the widget grid
# put it, in px at 100% scaling, so it looks the same: see `_layout`.
LABEL_H = 28            # a CTkLabel's least height
ENTRY_H, ENTRY_GAP = 48, 4
WRAP = 250              # the card's text wraps here, as the labels' wraplength did
CARD_W = 274            # the sidebar's width less 8 px each side
ROW_H = 20              # a Family line's least height


class EffortSidebar(ctk.CTkCanvas):
    WIDTH = 290

    def __init__(self, parent, theme, on_effort, on_head):
        super().__init__(parent, width=self.WIDTH, height=1, highlightthickness=0, borderwidth=0)
        self.on_effort, self.on_head = on_effort, on_head
        self.shapes = Shapes(self)
        self.px = Scale(self)
        self.items = Items(self)
        self.configure(width=self.px(self.WIDTH))
        self._args = None      # (efforts, shown, with_list) as last shown
        self._height = 1
        self._entries = []     # one per Effort in the list: (shape tag, text item)
        self._rows = []        # one per Family line: (name item, count item)
        self._hits = []        # (x0, y0, x1, y1, what) for clicks, hover and the cursor
        self._hover = None     # the list index under the pointer, or None
        self.hosted = None     # a widget drawn under the card: see host
        self._hosted_item = None
        self._header = self._text()
        self._title = self._text(justify="left")
        self._status = self._text(justify="left")
        self._share = self._text()
        self.bind("<Configure>", self._resized)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Button-1>", self._clicked)
        self.set_theme(theme)

    # ---------- called by the Board view ----------
    def host(self, widget):
        """Keep `widget` (a child of this sidebar: the header's Builders, 09) under the
        header card, 8 px below it: it draws itself and is never rebuilt here."""
        self.hosted = widget
        self._hosted_item = self.create_window(0, 0, window=widget, anchor="nw")
        self._render()

    def show(self, efforts, shown, with_list):
        """Draw the list of `efforts` (when `with_list`) and the card for the one named `shown`."""
        self._args = (tuple(efforts), shown, with_list)
        self._render()

    def set_theme(self, theme):
        """Draw in `theme` from now on: recolour, and re-lay out for its fonts, in place."""
        self.theme = t = theme
        s = self.px.factor
        self._mono = t.font("mono", "readout", scale=s)
        self._section = t.font("ui", "section", "bold", scale=s)
        self._title_font = t.font("ui", "header_title", "bold", scale=s)
        self.configure(bg=t["bg"])
        self._render()

    # ---------- drawing ----------
    def _text(self, **options):
        options = {"anchor": "nw", **options}
        return self.items.add(self.create_text(0, 0, state="hidden", tags="text", **options),
                              state="hidden")

    def _text_height(self, item):
        x0, y0, x1, y1 = self.bbox(item)
        return y1 - y0

    def _render(self):
        """Lay out and colour everything for the last `show`, touching only what changed."""
        t, px = self.theme, self.px
        self.shapes.rounded_rect("panel", 0, 0, px(self.WIDTH), self._height, px(8))
        self.shapes.colour("panel", inner=t["bg_panel"])
        if self._args is None:
            return
        efforts, shown, with_list = self._args
        self._hits = []
        line = self._mono.metrics("linespace")
        y = 0
        self.items.put(self._header, state="normal" if with_list else "hidden")
        if with_list:
            head_line = self._section.metrics("linespace")
            self.items.put(self._header, (px(12), px(10) + (px(LABEL_H) - head_line) // 2),
                      text="EFFORTS", fill=t["text_dim"], font=self._section)
            y = px(10) + px(LABEL_H) + px(4)
        label_h = max(px(LABEL_H), 2 * line)
        entry_h = max(px(ENTRY_H), label_h + 2 * px(5))
        listed = efforts if with_list else ()
        while len(self._entries) < len(listed):
            self._entries.append((f"entry{len(self._entries)}", self._text(justify="left")))
        for i, (tag, text) in enumerate(self._entries):
            if i >= len(listed):
                self.shapes.show(tag, False)
                self.items.put(text, state="hidden")
                continue
            effort = listed[i]
            front = effort.name == shown
            top = y + px(2)
            self.shapes.rounded_rect(tag, px(8), top, px(CARD_W), entry_h, px(6), px(1))
            self._paint_entry(i, front)
            closed, total = done_share(effort)
            self.items.put(text, (px(18), top + px(5) + (label_h - 2 * line) // 2), state="normal",
                      text=f"{effort.name}\n{KIND_LABEL[effort.kind]:<6}{closed:>3}/{total} done",
                      fill=t["text"] if front else t["text_muted"], font=self._mono)
            self._hits.append((px(8), top, px(8) + px(CARD_W), top + entry_h, ("entry", i)))
            y = top + entry_h + px(2)
        effort = next((e for e in efforts if e.name == shown), None)
        below = self._card(effort, y + px(16) if with_list else px(8), line)
        if self._hosted_item is not None:
            self.coords(self._hosted_item, px(8), y if below is None else below)
        self._restack()

    def _paint_entry(self, index, front):
        """An entry's box: selected for the Effort in front, raised under the pointer.
        A box in the panel's own colours is not drawn at all: its corners are rotated
        glyphs, slow to paint, and would not show."""
        t = self.theme
        if index == self._hover:
            fill = t["bg_raised"]
        else:
            fill = t["bg_select"] if front else t["bg_panel"]
        border = t["accent"] if front else t["bg_panel"]
        tag = self._entries[index][0]
        self.shapes.colour(tag, inner=fill, border=border)
        self.shapes.show(tag, fill != t["bg_panel"] or border != t["bg_panel"])

    def _card(self, effort, top, line):
        """Draw the header card at `top`; the y under it for a hosted widget, or None."""
        t, px = self.theme, self.px
        parts = (self._title, self._status, self._share)
        if effort is None:
            self.shapes.show("card", False)
            self.shapes.show("bar", False)
            for item in parts:
                self.items.put(item, state="hidden")
            for name, count in self._rows:
                self.items.put(name, state="hidden")
                self.items.put(count, state="hidden")
            return None
        left, right = px(20), px(8) + px(CARD_W) - px(12)
        # Title: wraps at WRAP, as tall as its lines (a label is at least LABEL_H).
        self.items.put(self._title, state="normal", text=effort.title or effort.name, width=px(WRAP),
                  fill=t["text"], font=self._title_font)
        y = top + px(10)
        text_h = self._text_height(self._title)
        title_h = max(px(LABEL_H), text_h)
        self.items.put(self._title, (left, y + (title_h - text_h) // 2))
        self._hits.append((left, y, left + px(WRAP), y + title_h, ("head", None)))
        y += title_h
        # Status: kind, the Map's or Spec's Status, and the stale-spec warning.
        status = KIND_LABEL[effort.kind]
        if effort.status:
            status += f": {effort.status}"
        if effort.stale_spec:
            status += "\n" + STALE_WARNING
        self.items.put(self._status, state="normal", text=status, width=px(WRAP), font=self._mono,
                  fill=t.family(NEEDS_ME) if effort.stale_spec else t["text_muted"])
        text_h = self._text_height(self._status)
        status_h = max(px(LABEL_H), text_h)
        self.items.put(self._status, (left, y + (status_h - text_h) // 2))
        y += status_h + px(8)
        # One line per Family: a dot and its name, its count on the right.
        counts = list(effort.counts.items())
        while len(self._rows) < len(counts):
            self._rows.append((self._text(), self._text(anchor="ne")))
        row_h = max(px(ROW_H), line)
        for i, (name, count) in enumerate(self._rows):
            if i >= len(counts):
                self.items.put(name, state="hidden")
                self.items.put(count, state="hidden")
                continue
            family, n = counts[i]
            colour = t.family(family) if n else t["text_dim"]
            text_y = y + (row_h - line) // 2
            self.items.put(name, (left, text_y), state="normal", text=f"● {family}", fill=colour,
                      font=self._mono)
            self.items.put(count, (right, text_y), state="normal", text=f"{n:>3}", fill=colour,
                      font=self._mono)
            y += row_h
        # The done-share bar and, under it, the share in words.
        closed, total = done_share(effort)
        y += px(10)
        self.shapes.progress_bar("bar", left, y, px(WRAP), px(10), px(5),
                                 closed / total if total else 0)
        self.shapes.colour("bar", inner=t["bg"], progress=t.family(DONE))
        self.shapes.show("bar", True)
        y += px(10) + px(2)
        share = f"{round(100 * closed / total)}%" if total else "no tickets"
        text = f"{closed}/{total} done  {share}"
        width = self._mono.measure(text)
        share_h = max(px(LABEL_H), line)
        self.items.put(self._share, (left + (px(WRAP) - width) // 2, y + (share_h - line) // 2),
                  state="normal", text=text, fill=t["text_muted"], font=self._mono)
        y += share_h + px(10)
        self.shapes.rounded_rect("card", px(8), top, px(CARD_W), y - top, px(8))
        self.shapes.colour("card", inner=t["bg_raised"])
        self.shapes.show("card", True)
        return y + px(8)   # where the next row started: the card's grid pady below it

    def _restack(self):
        """Panel at the bottom, then the list's entries, the card, its bar, and the text:
        after a shape is drawn anew, as its items start at the bottom."""
        if not self.shapes.restack:
            return
        self.shapes.restack = False
        for tag in ("panel", *(tag for tag, _ in self._entries), "card", "bar", "text"):
            self.tag_raise(tag)

    # ---------- events ----------
    def _resized(self, event):
        if event.height != self._height:
            self._height = event.height
            self.shapes.rounded_rect("panel", 0, 0, self.px(self.WIDTH), self._height, self.px(8))
            self._restack()

    def _hit(self, event):
        x, y = self.canvasx(event.x), self.canvasy(event.y)
        return next((what for x0, y0, x1, y1, what in self._hits
                     if x0 <= x < x1 and y0 <= y < y1), None)

    def _motion(self, event):
        what = self._hit(event)
        cursor = "hand2" if what else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)
        self._set_hover(what[1] if what and what[0] == "entry" else None)

    def _set_hover(self, index):
        if index == self._hover:
            return
        old, self._hover = self._hover, index
        efforts, shown, with_list = self._args or ((), None, False)
        for i in (old, index):
            if i is not None and with_list and i < len(efforts):
                self._paint_entry(i, efforts[i].name == shown)

    def _clicked(self, event):
        what = self._hit(event)
        if what is None:
            return
        kind, index = what
        if kind == "entry":
            self.on_effort(self._args[0][index].name)
        else:
            self.on_head()
