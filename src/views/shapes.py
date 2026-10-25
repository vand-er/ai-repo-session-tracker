"""CustomTkinter's rounded shapes, many on one canvas.

A CustomTkinter frame, button or progress bar is a window of its own with a canvas that
draws one rounded shape. Each window costs time whenever it is mapped, raised or
repainted, so the parts of the window that must redraw in 20 ms (the Effort sidebar, the
tab strip, the options bar) draw their shapes as items on one canvas instead. The shapes
come from CustomTkinter's own DrawEngine, so they are the same pixels: it draws one shape
at the canvas origin under fixed tags, and `Shapes` renames those items to the shape's
own tag and moves them into place. Those tags ("inner_parts" and the like) are a
CustomTkinter internal, kept because there is no public way to draw its shapes on a
shared canvas; they are read through the adapter (`engine_part_items` in
src/views/ctk_internals.py), so a CustomTkinter update that renames them shows there.

    shapes = Shapes(canvas)                       # canvas: a ctk.CTkCanvas
    shapes.rounded_rect("card", x, y, w, h, radius=8)
    shapes.colour("card", inner=palette["bg_raised"])
    shapes.progress_bar("bar", x, y, w, h, radius=5, value=0.7)
    shapes.colour("bar", inner=bg, progress=done)

Two helpers every canvas-drawn part shares sit beside it:

    px = Scale(canvas)            # px(8): 8 px at 100%, at CustomTkinter's widget scaling
    items = Items(canvas)
    items.put(text, (x, y), fill=colour, text="…")   # calls Tk only for what changed
"""

import tkinter as tk

import customtkinter as ctk

from src.views.ctk_internals import engine_part_items

PARTS = ("border", "inner", "progress")


class Scale:
    """Px at 100% scaling to px at the widget's CustomTkinter scaling, as CustomTkinter
    scales its own widgets: `px(8)`. `factor` is the scaling itself, for fonts."""

    def __init__(self, widget):
        self.factor = ctk.ScalingTracker.get_widget_scaling(widget)

    def __call__(self, n):
        return round(n * self.factor)


class Items:
    """A canvas's items with the coords and options each was last given, so that setting
    them again calls Tk only for what has changed: each call repaints the item."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._known = {}     # item -> {option: value, "coords": coords} as last set

    def add(self, item, **options):
        """Note a new `item`, made with `options`; returns it."""
        self._known[item] = dict(options)
        return item

    def put(self, item, coords=None, **options):
        """Set `item`'s coords (when given) and options, calling Tk only for what has
        changed. Plain Tk calls: a CTkCanvas's own only add its anti-aliased circles."""
        known = self._known.setdefault(item, {})
        if coords is not None and known.get("coords") != coords:
            known["coords"] = coords
            tk.Canvas.coords(self.canvas, item, *coords)
        changed = {k: v for k, v in options.items() if known.get(k) != v}
        if changed:
            known.update(changed)
            tk.Canvas.itemconfigure(self.canvas, item, **changed)


class Shapes:
    def __init__(self, canvas):
        self.canvas = canvas
        self._engine = ctk.DrawEngine(canvas)
        self._items = {}     # tag -> {part: [(item, is_text)]}
        self._drawn = {}     # tag -> the arguments it was drawn with
        self._colours = {}   # tag -> {part: colour} as last asked for
        self._applied = {}   # tag -> {part: colour} as its items have them
        self._hidden = set() # tags hidden with show(tag, False)
        self._engine_tags = {}   # item -> the tags the engine gave it
        # Set when a shape is (re)drawn: its new items sit at the bottom of the canvas, so
        # the owner should restack (and clear this).
        self.restack = False

    def rounded_rect(self, tag, x, y, w, h, radius, border=0):
        """A rounded rectangle at x, y, as a CTkFrame of that size draws it (sizes are
        floored to even, as CustomTkinter does). Redrawn only when its geometry changes."""
        self._draw(tag, (x, y), ("rect", w, h, radius, border),
                   lambda: self._engine.draw_rounded_rect_with_border(w, h, radius, border))

    def progress_bar(self, tag, x, y, w, h, radius, value, border=0):
        """A CTkProgressBar's bar, filled from the left to `value` (0 to 1)."""
        self._draw(tag, (x, y), ("bar", w, h, radius, border, value),
                   lambda: self._engine.draw_rounded_progress_bar_with_border(
                       w, h, radius, border, 0, value, "w"))

    def colour(self, tag, **colours):
        """Colour a shape's parts: `inner`, `border`, `progress`. Only what changed, and a
        hidden shape only when it is shown again: recolouring a corner glyph is slow."""
        self._colours.setdefault(tag, {}).update(colours)
        if tag not in self._hidden:
            self._apply(tag)

    def _apply(self, tag):
        applied = self._applied.setdefault(tag, {})
        for part, colour in self._colours.get(tag, {}).items():
            if applied.get(part) == colour:
                continue
            applied[part] = colour
            for item, is_text in self._items.get(tag, {}).get(part, ()):
                if is_text:    # a corner, drawn as a glyph of CustomTkinter's shapes font
                    self.canvas.itemconfigure(item, fill=colour)
                else:
                    self.canvas.itemconfigure(item, fill=colour, outline=colour)

    def show(self, tag, shown):
        if shown == (tag in self._hidden):
            if shown:
                self._hidden.discard(tag)
                self._apply(tag)
            else:
                self._hidden.add(tag)
            self.canvas.itemconfigure(tag, state="normal" if shown else "hidden")

    def _draw(self, tag, at, geometry, draw):
        canvas = self.canvas
        drawn = self._drawn.get(tag)
        if drawn is not None and drawn[1] == geometry:
            if drawn[0] != at:
                canvas.move(tag, at[0] - drawn[0][0], at[1] - drawn[0][1])
                self._drawn[tag] = (at, geometry)
            return
        # A shape of another size reuses its items: they get back the engine's tags, so the
        # engine only moves them (making a corner glyph is the slow part), then lose them.
        old = [item for part in self._items.get(tag, {}).values() for item, _ in part]
        for item in old:
            canvas.itemconfigure(item, tags=self._engine_tags[item])
        before = set(old)
        draw()
        items, created = {}, False
        for part in PARTS:
            for item in engine_part_items(canvas, part):
                if item not in before:
                    created = True
                    self._engine_tags[item] = canvas.gettags(item)
                    if tag in self._hidden:
                        canvas.itemconfigure(item, state="hidden")
                canvas.itemconfigure(item, tags=(tag, f"{tag}.{part}"))
                items.setdefault(part, []).append((item, canvas.type(item) == "text"))
        for item in before - {i for part in items.values() for i, _ in part}:
            self._engine_tags.pop(item, None)   # dropped by the engine
        canvas.move(tag, *at)
        self._items[tag] = items
        self._drawn[tag] = (at, geometry)
        if created:   # new items have no colour yet: colour them all
            self.restack = True
            self._applied.pop(tag, None)
            if tag not in self._hidden:
                self._apply(tag)
