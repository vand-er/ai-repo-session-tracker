"""The detail pane under the Ticket table: the selected file's title and full path, Copy
path and Copy command buttons, and its body, read-only and monospaced. Under the body, a
Ticket being built shows its Builder's last message (08), cut to MESSAGE_LINES or fewer,
so the body keeps BODY_MIN_LINES. It reads
no files: the controller reads the file on click and hands over a model `Detail`.

The pane, its title, path and buttons are drawn on one canvas (fast-live-board 04): as
CustomTkinter labels and buttons they were fifteen windows, each repainted whenever the
Board came to the front or was restyled. Each item sits where the widget grid put it, in
px at 100% scaling. The body is still a CTkTextbox, placed on the canvas."""

import tkinter as tk

import customtkinter as ctk

from src.model.detail import fit_message
from src.views.shapes import Items, Scale, Shapes

PROMPT = "Select a Ticket to see its file."
MESSAGE_PREFIX = "Builder: "   # before a Ticket being built's Builder's last message
MESSAGE_LINES = 3              # at most; fewer when the body would keep under BODY_MIN_LINES
BODY_MIN_LINES = 3
MESSAGE_PADY = 10              # px under the message line; the body keeps BODY_BOTTOM over it
COPIED = "Copied"
COPIED_MS = 1200

PADX, TITLE_TOP, LABEL_H = 12, 8, 28      # a CTkLabel is at least LABEL_H tall
WRAP_LESS = 40                             # the title and path wrap at the width less this
BUTTON_W, BUTTON_H, BUTTON_GAP, BUTTON_PADY = 120, 26, 6, 6
CORNER, LABEL_BD, SPACING = 4, 1, 2        # a CTkButton's corner, text border and padding
BODY_BOTTOM, BODY_CORNER = 12, 6
BUTTONS = (("path", "Copy path"), ("command", "Copy command"))


def _scrollbar_colours(theme):
    """The body's scrollbar in CustomTkinter's own colours for the palette's light or dark
    mode, given outright: a theme switch no longer flips the toolkit's appearance mode,
    which redrew every widget in the window."""
    return {"scrollbar_button_color": theme.ctk_default("CTkScrollbar", "button_color"),
            "scrollbar_button_hover_color": theme.ctk_default("CTkScrollbar",
                                                              "button_hover_color")}


class DetailPane(ctk.CTkCanvas):
    HEIGHT = 270

    def __init__(self, parent, theme):
        super().__init__(parent, height=1, highlightthickness=0, borderwidth=0)
        self.px = Scale(self)
        self.height = self.px(self.HEIGHT)
        self.configure(height=self.height)
        self.theme = theme
        self.detail = None
        self.shapes = Shapes(self)
        self.items = Items(self)
        self._width = 1
        self._title = self.create_text(0, 0, anchor="nw", justify="left", tags="text")
        self._path = self.create_text(0, 0, anchor="nw", justify="left", tags="text")
        self._labels = {key: label for key, label in BUTTONS}   # text shown on each button
        self._button_text = {key: self.create_text(0, 0, anchor="nw", tags=("text", "buttons"))
                             for key, _ in BUTTONS}
        self._buttons = {}      # key -> (x0, y0, x1, y1) while the buttons show
        self._hover = self._pressed = None
        self.body = ctk.CTkTextbox(self, corner_radius=BODY_CORNER, wrap="word", border_width=0)
        self._body_style = {}
        # A Ticket being built: its Builder's last message under the body, cut to
        # MESSAGE_LINES (08).
        self._message_item = self.create_text(0, 0, anchor="nw", justify="left", tags="text",
                                              state="hidden")
        self._message = None
        self.bind("<Configure>", self._resized)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.set_theme(theme)
        self.clear()

    def set_theme(self, theme):
        """Recolour in `theme`, in place, keeping what is shown."""
        self.theme = t = theme
        s = self.px.factor
        self._title_font = t.font("ui", "detail_title", "bold", scale=s)
        self._path_font = t.font("mono", "detail", scale=s)
        self._button_font = t.font("ui", "ui", scale=s)
        self.configure(bg=t["bg"])
        self.items.put(self._title, fill=t["text"], font=self._title_font)
        self.items.put(self._path, fill=t["text_muted"], font=self._path_font)
        self.items.put(self._message_item, fill=t["accent"], font=self._path_font)
        for item in self._button_text.values():
            self.items.put(item, fill=t["text"], font=self._button_font)
        body = {"fg_color": t["bg"], "bg_color": t["bg_panel"], "text_color": t["text"],
                "font": t.mono("detail"), **_scrollbar_colours(t)}
        # Only what changes: each option redraws the textbox's two scrollbars.
        same = {k: v for k, v in body.items() if k != "font"}
        same["font"] = (t.mono_family, t.pt("detail"))   # a new theme's font object, same font
        changed = [k for k, v in same.items() if self._body_style.get(k) != v]
        if changed:
            self._body_style.update(same)
            self.body.configure(**{k: body[k] for k in changed})
        self._layout()

    # ---------- called by the Board view ----------
    def clear(self):
        self.detail = None
        self._message = None
        self.show_file(PROMPT, "")
        self._set_body("")

    def show_file(self, title, path):
        self.items.put(self._title, text=title)
        self.items.put(self._path, text=str(path))
        self._layout()

    def show_detail(self, detail):
        """Show a model `Detail`: its path, the copy buttons and its body."""
        self.detail = detail
        self._message = detail.last_message
        self.items.put(self._path, text=str(detail.path))
        self._set_body(detail.body)
        self._layout()

    # ---------- drawing ----------
    def _text_height(self, item):
        """The text's height as laid out; an empty text is as tall as nothing (a label
        with no text is still LABEL_H tall)."""
        box = self.bbox(item)
        return box[3] - box[1] if box else 0

    def _layout(self):
        """Place everything for the pane's width and what it shows, as its grid did."""
        t, px = self.theme, self.px
        self.shapes.rounded_rect("pane", 0, 0, self._width, self.height, px(8))
        self.shapes.colour("pane", inner=t["bg_panel"])
        wrap = max(self._width - px(WRAP_LESS), 100)
        y = px(TITLE_TOP)
        for item in (self._title, self._path):
            self.items.put(item, width=wrap)
            text_h = self._text_height(item)
            label_h = max(px(LABEL_H), text_h)
            self.items.put(item, (px(PADX), y + (label_h - text_h) // 2))
            y += label_h
        shown = self.detail is not None
        self._buttons = {}
        if shown:
            y += px(BUTTON_PADY)
            line = self._button_font.metrics("linespace") + 2 * px(LABEL_BD)
            h = max(px(BUTTON_H), line + 2 * px(SPACING))
            x = px(PADX)
            for key, _ in BUTTONS:
                w = px(BUTTON_W)
                text = self._labels[key]
                label_w = self._button_font.measure(text) + 2 * px(LABEL_BD)
                self.items.put(self._button_text[key], (x + (w - label_w) // 2 + px(LABEL_BD),
                                                   y + (h - line) // 2 + px(LABEL_BD)), text=text)
                self.shapes.rounded_rect(f"button-{key}", x, y, w, h, px(CORNER))
                self.shapes.colour(f"button-{key}",
                                   inner=t["bg_select"] if key == self._hover else t["bg_raised"])
                self._buttons[key] = (x, y, x + w, y + h)
                x += w + px(BUTTON_GAP)
            y += h + px(BUTTON_PADY)
        for key, _ in BUTTONS:
            self.shapes.show(f"button-{key}", shown)
        for item in self._button_text.values():
            self.items.put(item, state="normal" if shown else "hidden")
        if self.shapes.restack:
            self.shapes.restack = False
            self.tag_raise("button-path")
            self.tag_raise("button-command")
            self.tag_raise("text")
        bottom = self.height - self._layout_message(y)
        body = (px(PADX), y, self._width - 2 * px(PADX), bottom - y - px(BODY_BOTTOM))
        if body != getattr(self, "_body_at", None):
            self._body_at = body
            # In px already: CustomTkinter's own place() refuses a width and height.
            tk.Place.place_configure(self.body, x=body[0], y=body[1], width=max(body[2], 1),
                                     height=max(body[3], 1))

    def _message_lines(self, body_top):
        """How many lines the message may take: MESSAGE_LINES, or fewer (down to one) so
        that the body above it keeps BODY_MIN_LINES in view (08: the cut is to what the
        pane shows without scrolling, and must not crowd out the body). In the larger
        fonts (frost, onyx, plum) three lines left the body about one and a half."""
        px, line = self.px, self._path_font.metrics("linespace")
        for lines in range(MESSAGE_LINES, 1, -1):
            label_h = max(px(LABEL_H), lines * line)
            body_h = (self.height - px(MESSAGE_PADY) - label_h - body_top - px(BODY_BOTTOM)
                      - 2 * px(BODY_CORNER))   # the textbox's own inset
            if body_h >= BODY_MIN_LINES * line:
                return lines
        return 1

    def _layout_message(self, body_top):
        """Place the Builder's last message at the pane's foot, as its label's grid row
        did, cut to the width and to `_message_lines`; the px it takes from the bottom (0
        when there is none). `body_top` is where the body starts."""
        px = self.px
        if not self._message:
            self.items.put(self._message_item, state="hidden")
            return 0
        char = max(1, self._path_font.measure("0"))
        columns = (max(self._width, 200) - px(WRAP_LESS)) // char - len(MESSAGE_PREFIX)
        lines = self._message_lines(body_top)
        text = MESSAGE_PREFIX + fit_message(self._message, columns, lines).replace(
            "\n", "\n" + " " * len(MESSAGE_PREFIX))
        self.items.put(self._message_item, text=text, state="normal")
        text_h = self._text_height(self._message_item)
        label_h = max(px(LABEL_H), text_h)
        top = self.height - px(MESSAGE_PADY) - label_h
        self.items.put(self._message_item, (px(PADX), top + (label_h - text_h) // 2))
        return label_h + px(MESSAGE_PADY)

    def _set_body(self, text):
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", text)
        self.body.configure(state="disabled")

    # ---------- events ----------
    def _resized(self, event):
        if event.width != self._width:
            self._width = event.width
            self._layout()

    def _hit(self, event):
        return next((key for key, (x0, y0, x1, y1) in self._buttons.items()
                     if x0 <= event.x < x1 and y0 <= event.y < y1), None)

    def _motion(self, event):
        self._set_hover(self._hit(event))

    def _set_hover(self, key):
        """A button under the pointer shows its hover colour, as a CTkButton did."""
        if key == self._hover:
            return
        for old_new in (self._hover, key):
            if old_new is not None and old_new in self._buttons:
                colour = "bg_select" if old_new == key else "bg_raised"
                self.shapes.colour(f"button-{old_new}", inner=self.theme[colour])
        self._hover = key
        cursor = "hand2" if key else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)

    def _press(self, event):
        self._pressed = self._hit(event)

    def _release(self, event):
        """A CTkButton runs its command on release, over the button pressed."""
        key, self._pressed = self._pressed, None
        if key is None or key != self._hit(event) or self.detail is None:
            return
        self._copy(key, str(self.detail.path) if key == "path" else self.detail.command)

    def _copy(self, key, text):
        """Put `text` on the clipboard (the toolkit's own) and say so on the button."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()  # keeps the text on the clipboard after the app quits
        self._show_label(key, COPIED)
        self.after(COPIED_MS, lambda: self.winfo_exists() and
                   self._show_label(key, dict(BUTTONS)[key]))

    def _show_label(self, key, text):
        self._labels[key] = text
        self._layout()
