"""The tab strip under the options bar: one button per open tab with a close mark, then
"+ New tab". It draws titles it is given and reports clicks; it owns no tab state.

It is drawn on one canvas (fast-live-board 04): it was CustomTkinter frames and buttons,
destroyed and rebuilt on every tab switch. Each tab is still CTkFrame's rounded box
(`src/views/shapes.py`) holding two flat CTkButtons, placed where their grid put them,
so it looks the same; a switch only recolours the two tabs that change."""

import customtkinter as ctk

from src.views.shapes import Items, Scale, Shapes

# CTkButton's geometry at 100%: its text label has a 1 px border, the label is padded by
# the corner radius left and right and 2 px above and below.
CORNER, LABEL_BD, SPACING = 6, 1, 2
TAB_PAD, TAB_GAP = 2, 6           # a tab's buttons sit 2 px inside its box; 6 px between tabs
TITLE_W, CLOSE_W, BUTTON_H = 40, 24, 26
NEW_W, NEW_H = 120, 30
NEW_TEXT, CLOSE_TEXT = "+  New tab", "×"


class TabStrip(ctk.CTkCanvas):
    def __init__(self, parent, theme, on_front, on_close, on_new):
        super().__init__(parent, height=1, highlightthickness=0, borderwidth=0)
        self.on_front, self.on_close, self.on_new = on_front, on_close, on_new
        self.titles, self.active = [], None
        self.shapes = Shapes(self)
        self.px = Scale(self)
        self.items = Items(self)
        self._tabs = []       # per tab: (box tag, title text, close text)
        self._buttons = []    # (x0, y0, x1, y1, what): what is ("front"|"close", i) or ("new",)
        self._hover = None    # the button under the pointer
        self._new_text = self._text()
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        # A CTkButton runs its command on release, over the button pressed.
        self._pressed = None
        self.bind("<Button-1>", lambda e: setattr(self, "_pressed", self._hit(e)))
        self.bind("<ButtonRelease-1>", self._clicked)
        self.set_theme(theme)

    # ---------- called by the window ----------
    def set_theme(self, theme):
        self.theme = theme
        self._font = theme.font("ui", "ui", scale=self.px.factor)
        self.configure(bg=theme["bg"])
        self.redraw()

    def set_tabs(self, titles, active):
        self.titles, self.active = list(titles), active
        self.redraw()

    def redraw(self):
        """Lay out and colour the tabs, touching only what changed."""
        t, px = self.theme, self.px
        line = self._font.metrics("linespace") + 2 * px(LABEL_BD)
        button_h = max(px(BUTTON_H), line + 2 * px(SPACING))
        tab_h = button_h + 2 * px(TAB_PAD)
        new_h = max(px(NEW_H), line + 2 * px(SPACING))
        height = max(tab_h, new_h)
        if int(self.cget("height")) != height:
            self.configure(height=height)
        while len(self._tabs) < len(self.titles):
            n = len(self._tabs)
            self._tabs.append((f"tab{n}", self._text(), self._text()))
        self._buttons = []
        x = 0
        for i, (box, title_item, close_item) in enumerate(self._tabs):
            if i >= len(self.titles):
                self.shapes.show(box, False)
                for what in (("front", i), ("close", i)):
                    self.shapes.show(self._hover_tag(what), False)
                self.items.put(title_item, state="hidden")
                self.items.put(close_item, state="hidden")
                continue
            front = i == self.active
            title_w = max(px(TITLE_W), self._label_w(self.titles[i]) + 2 * px(CORNER))
            close_w = max(px(CLOSE_W), self._label_w(CLOSE_TEXT) + 2 * px(CORNER))
            width = title_w + close_w + 2 * px(TAB_PAD)
            y = (height - tab_h) // 2
            self.shapes.rounded_rect(box, x, y, width, tab_h, px(CORNER), px(1))
            self.shapes.colour(box, inner=t["bg_raised"] if front else t["bg"],
                               border=t["accent"] if front else t["line"])
            self.shapes.show(box, True)
            bx, by = x + px(TAB_PAD), y + px(TAB_PAD)
            self._button(("front", i), title_item, self.titles[i], bx, by, title_w, button_h,
                         t["text"] if front else t["text_muted"])
            self._button(("close", i), close_item, CLOSE_TEXT, bx + title_w, by, close_w,
                         button_h, t["text_muted"])
            x += width + px(TAB_GAP)
        new_w = max(px(NEW_W), self._label_w(NEW_TEXT) + 2 * px(CORNER))
        y = (height - new_h) // 2
        self.shapes.rounded_rect("new", x, y, new_w, new_h, px(CORNER), px(1))
        self.shapes.colour("new", inner=t["bg"], border=t["line"])
        self._button(("new",), self._new_text, NEW_TEXT, x, y, new_w, new_h, t["text_muted"],
                     inset=px(1))
        self._restack()

    # ---------- drawing ----------
    def _text(self):
        return self.items.add(self.create_text(0, 0, anchor="nw", state="hidden", tags="text"),
                              state="hidden")

    def _label_w(self, text):
        return self._font.measure(text) + 2 * self.px(LABEL_BD)

    @staticmethod
    def _hover_tag(what):
        return "hover-" + "-".join(map(str, what))

    def _button(self, what, item, text, x, y, w, h, colour, inset=0):
        """A flat CTkButton: its text centred as its grid centres the label, and a rounded
        box in the hover colour under the pointer (`inset` keeps a border showing)."""
        line = self._font.metrics("linespace") + 2 * self.px(LABEL_BD)
        label_w = self._label_w(text)
        self.items.put(item, (x + (w - label_w) // 2 + self.px(LABEL_BD),
                         y + (h - line) // 2 + self.px(LABEL_BD)),
                  state="normal", text=text, fill=colour, font=self._font)
        tag = self._hover_tag(what)
        if inset:
            self.shapes.rounded_rect(tag, x, y, w, h, self.px(CORNER), inset)
            self.shapes.colour(tag, inner=self.theme["bg_select"], border=self.theme["line"])
        else:
            self.shapes.rounded_rect(tag, x, y, w, h, self.px(CORNER))
            self.shapes.colour(tag, inner=self.theme["bg_select"])
        self.shapes.show(tag, what == self._hover)
        self._buttons.append((x, y, x + w, y + h, what))

    def _restack(self):
        if not self.shapes.restack:
            return
        self.shapes.restack = False
        for box, _, _ in self._tabs:
            self.tag_raise(box)
        self.tag_raise("new")
        for _, _, _, _, what in self._buttons:
            self.tag_raise(self._hover_tag(what))
        self.tag_raise("text")

    # ---------- events ----------
    def _hit(self, event):
        return next((what for x0, y0, x1, y1, what in self._buttons
                     if x0 <= event.x < x1 and y0 <= event.y < y1), None)

    def _motion(self, event):
        self._set_hover(self._hit(event))

    def _set_hover(self, what):
        if what == self._hover:
            return
        for old in (self._hover,):
            if old is not None:
                self.shapes.show(self._hover_tag(old), False)
        self._hover = what
        if what is not None:
            self.shapes.show(self._hover_tag(what), True)
        cursor = "hand2" if what else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)

    def _clicked(self, event):
        what, self._pressed = self._pressed, None
        if what is None or what != self._hit(event):
            return
        if what[0] == "front":
            self.on_front(what[1])
        elif what[0] == "close":
            self.on_close(what[1])
        else:
            self.on_new()
