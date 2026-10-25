"""The Builders in an Effort's header: each Builder working in the Effort on no Ticket of
it (such as one fixing a code review's findings), with its Activity. Clicking one calls
`on_open(transcript)`, which opens its Session in the Sessions tab.

One small canvas, hosted by the Effort sidebar under the header card (`EffortSidebar.host`)
and as wide as the card. Its box is the card's rounded shape (`src/views/shapes.py`).
`show(entries)` re-configures the items it has drawn and adds one only for a new Builder;
nothing is destroyed. With no Builders it is a 1 px strip in the sidebar's colour. It
reads no files and imports nothing of the model.

    builders = HeaderBuilders(sidebar, theme, on_open)
    sidebar.host(builders)
    builders.show([(transcript, "Fix the code review's findings · Running tests · 4s")])
    builders.set_theme(theme)        # recolour in place
"""

import customtkinter as ctk

from src.views.effort_sidebar import CARD_W
from src.views.shapes import Items, Scale, Shapes

HEADING = "BUILDERS"
PAD_X, PAD_Y, GAP = 12, 10, 6
WRAP = CARD_W - 2 * PAD_X
RADIUS = 8
MARK = "▸ "


class HeaderBuilders(ctk.CTkCanvas):
    def __init__(self, parent, theme, on_open):
        super().__init__(parent, width=CARD_W, height=1, highlightthickness=0, borderwidth=0)
        self.px = Scale(self)
        self.items = Items(self)
        self.shapes = Shapes(self)
        self.configure(width=self.px(CARD_W))
        self.on_open = on_open
        self._entries = ()     # ((transcript, text), ...) as last shown
        self._texts = []       # one text item per entry, reused
        self._hits = []        # (y0, y1, transcript) of each entry, for clicks
        self._height = 1
        self._heading = self._text(text=HEADING)
        self.bind("<Button-1>", self._clicked)
        self.bind("<Motion>", self._motion)
        self.set_theme(theme)

    # ---------- called by the Board view ----------
    def show(self, entries):
        """Show `entries`, `(transcript, text)` each, in order; none hides the box."""
        entries = tuple(entries)
        if entries != self._entries:
            self._entries = entries
            self._layout()

    def set_theme(self, theme):
        """Draw in `theme` from now on, in place."""
        self.theme = t = theme
        self._font = t.point_font("mono", "readout")
        self._head_font = t.point_font("ui", "section", "bold")
        self.configure(bg=t["bg_panel"])
        self.shapes.colour("box", inner=t["bg_raised"])
        self.items.put(self._heading, fill=t["text_dim"], font=self._head_font)
        for item in self._texts:
            self.items.put(item, fill=t["accent"], font=self._font)
        self._layout()

    # ---------- drawing ----------
    def _text(self, **options):
        return self.items.add(self.create_text(0, 0, anchor="nw", state="hidden", tags="text",
                                               **options), state="hidden", **options)

    def _layout(self):
        entries, px, put = self._entries, self.px, self.items.put
        while len(self._texts) < len(entries):
            self._texts.append(self._text(width=px(WRAP)))
            put(self._texts[-1], fill=self.theme["accent"], font=self._font)
        self._hits = []
        if not entries:
            self.shapes.show("box", False)
            for item in (self._heading, *self._texts):
                put(item, state="hidden")
            self._set_height(1)
            return
        put(self._heading, (px(PAD_X), px(PAD_Y)), state="normal")
        y = px(PAD_Y) + self._head_font.metrics("linespace") + px(GAP)
        for i, item in enumerate(self._texts):
            if i >= len(entries):
                put(item, state="hidden")
                continue
            transcript, text = entries[i]
            put(item, (px(PAD_X), y), text=MARK + text, state="normal")
            x0, y0, x1, y1 = self.bbox(item)
            self._hits.append((y, y1, transcript))
            y = y1 + px(GAP)
        height = y - px(GAP) + px(PAD_Y)
        self.shapes.rounded_rect("box", 0, 0, px(CARD_W), height, px(RADIUS))
        self.shapes.show("box", True)
        if self.shapes.restack:   # a box drawn anew starts under everything
            self.shapes.restack = False
            self.tag_raise("text")
        self._set_height(height)

    def _set_height(self, height):
        if height != self._height:
            self._height = height
            self.configure(height=height)

    # ---------- events ----------
    def _hit(self, event):
        return next((t for y0, y1, t in self._hits if y0 <= event.y < y1), None)

    def _motion(self, event):
        cursor = "hand2" if self._hit(event) is not None else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)

    def _clicked(self, event):
        transcript = self._hit(event)
        if transcript is not None:
            self.on_open(transcript)
