"""The options bar: the app's own menu bar, drawn from the palette (no native OS menu).

Menus are registered by name and drawn in MENU_ORDER, so a later ticket adds its items
without touching this file:

    bar.add_item("Actions", "Open in Explorer", command)
    bar.add_item("View", "Show detail pane", command, checked=lambda: shown)

A menu with no items is not drawn. Items keep the order they were added in. An item can
open a submenu beside it instead of running a command (View → Theme does):

    bar.add_submenu("View", "Theme", lambda: [MenuItem(name, cmd, checked), ...])
"""

from collections import namedtuple
from dataclasses import dataclass

import customtkinter as ctk

from src.views.shapes import Items, Scale, Shapes

MENU_ORDER = ("File", "View", "Actions", "Help")
# A menu button drawn on the bar: its box on the canvas and its menu's name.
Button = namedtuple("Button", "x0 y0 x1 y1 name")
# A menu button's geometry at 100%, as its CTkButton had it: at least 64 x 28, its text
# label (1 px border) padded by the corner radius, 3 px above and below in the bar, the
# first button 6 px from the left.
BUTTON_W, BUTTON_H, CORNER, LABEL_BD, SPACING = 64, 28, 4, 1, 2
BAR_PADX, BAR_PADY = 6, 3


@dataclass
class MenuItem:
    label: str
    command: object
    checked: object = None   # a callable giving True/False for a tick mark, or None
    separator_before: bool = False
    submenu: object = None   # a callable giving the submenu's MenuItems, or None


class OptionsBar(ctk.CTkCanvas):
    """The bar is drawn on one canvas (fast-live-board 04): each menu is a flat CTkButton's
    look, its text centred in at least BUTTON_W x BUTTON_H, a rounded box in the hover
    colour under the pointer. A theme switch recolours it in place."""

    def __init__(self, parent, theme):
        super().__init__(parent, height=1, highlightthickness=0, borderwidth=0)
        self.menus = {name: [] for name in MENU_ORDER}
        self.dropdown = None
        self.subdropdown = None
        # Called with each new dropdown in place of raising it on top: a scripted still
        # (`--shot`) keeps its menus behind, unfocused (src/views/placement.py).
        self.place_popup = None
        self.shapes = Shapes(self)
        self.px = Scale(self)
        self.items = Items(self)
        self._texts = {}      # menu name -> its text item
        self._buttons = []    # each menu's Button, drawn left to right
        self._hover = None
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        # A CTkButton runs its command on release, over the button pressed.
        self._pressed = None
        self.bind("<Button-1>", lambda e: setattr(self, "_pressed", self._hit(e)))
        self.bind("<ButtonRelease-1>", self._clicked)
        self.theme = theme
        self.set_theme(theme)
        root = self.winfo_toplevel()
        root.bind("<Button-1>", self._click_outside, add="+")
        root.bind("<Escape>", lambda _e: self.close_dropdown(), add="+")
        root.bind("<Configure>", lambda e: e.widget is root and self.close_dropdown(), add="+")

    def add_item(self, menu, label, command, checked=None, separator_before=False):
        self.menus.setdefault(menu, []).append(MenuItem(label, command, checked, separator_before))
        self.redraw()

    def add_submenu(self, menu, label, items, separator_before=False):
        """An item of `menu` that opens a submenu; `items()` gives its MenuItems each time
        it opens, so the list and its ticks are always current."""
        self.menus.setdefault(menu, []).append(
            MenuItem(label, None, separator_before=separator_before, submenu=items))
        self.redraw()

    def set_theme(self, theme):
        """Recolour the bar and its menu buttons in `theme`, in place."""
        self.theme = theme
        self._font = theme.font("ui", "ui", scale=self.px.factor)
        self.configure(bg=theme["bg_panel"])
        self.redraw()

    def redraw(self):
        """Lay out the menus that have items, left to right, touching only what changed."""
        self.close_dropdown()
        t, px = self.theme, self.px
        line = self._font.metrics("linespace") + 2 * px(LABEL_BD)
        h = max(px(BUTTON_H), line + 2 * px(SPACING))
        if int(self.cget("height")) != h + 2 * px(BAR_PADY):
            self.configure(height=h + 2 * px(BAR_PADY))
        x, y = px(BAR_PADX), px(BAR_PADY)
        self._buttons = []
        for name, items in self.menus.items():
            text = self._texts.get(name)
            if not items:
                if text is not None:
                    self.items.put(text, state="hidden")
                    self.shapes.show(f"hover-{name}", False)
                continue
            if text is None:
                text = self._texts[name] = self.create_text(0, 0, anchor="nw", tags="text")
            label_w = self._font.measure(name) + 2 * px(LABEL_BD)
            w = max(px(BUTTON_W), label_w + 2 * px(CORNER))
            self.items.put(text, (x + (w - label_w) // 2 + px(LABEL_BD),
                                  y + (h - line) // 2 + px(LABEL_BD)),
                           text=name, fill=t["text"], font=self._font, state="normal")
            tag = f"hover-{name}"
            self.shapes.rounded_rect(tag, x, y, w, h, px(CORNER))
            self.shapes.colour(tag, inner=t["bg_raised"])
            self.shapes.show(tag, name == self._hover)
            self._buttons.append(Button(x, y, x + w, y + h, name))
            x += w
        if self.shapes.restack:
            self.shapes.restack = False
            self.tag_raise("text")

    def _hit(self, event):
        return next((b for b in self._buttons
                     if b.x0 <= event.x < b.x1 and b.y0 <= event.y < b.y1), None)

    def _motion(self, event):
        button = self._hit(event)
        self._set_hover(button.name if button else None)

    def _set_hover(self, name):
        if name == self._hover:
            return
        if self._hover is not None:
            self.shapes.show(f"hover-{self._hover}", False)
        self._hover = name
        if name is not None:
            self.shapes.show(f"hover-{name}", True)
        cursor = "hand2" if name else ""
        if self.cget("cursor") != cursor:
            self.configure(cursor=cursor)

    def _clicked(self, event):
        button, self._pressed = self._pressed, None
        if button is not None and button == self._hit(event):
            self.open_dropdown(button, button.name)

    def open_dropdown(self, button, name):
        """Open `name`'s menu under its Button on the bar; a second click on an open menu
        closes it."""
        was_open = self.dropdown is not None and self.dropdown.menu_name == name
        self.close_dropdown()
        if was_open:
            return
        menu = self._popup(self.menus[name], self.winfo_rootx() + button.x0,
                           self.winfo_rooty() + button.y1)
        menu.menu_name = name
        self.dropdown = menu

    def open_menu(self, name):
        """Open the menu `name` as a click on its button does (`--menu`); nothing when it
        isn't drawn. Returns the dropdown, or None."""
        self.update_idletasks()
        button = next((b for b in self._buttons if b.name == name), None)
        if button is not None and (self.dropdown is None or self.dropdown.menu_name != name):
            self.open_dropdown(button, name)
        return self.dropdown

    def open_popups(self):
        """The dropdown and submenu open now, in that order."""
        return [m for m in (self.dropdown, self.subdropdown) if m is not None]

    def open_submenu(self, row_button, item):
        """Open `item`'s submenu beside its row in the open dropdown."""
        if self.subdropdown is not None and self.subdropdown.parent_label == item.label:
            return
        self.close_submenu()
        self.subdropdown = self._popup(item.submenu(),
                                       row_button.winfo_rootx() + row_button.winfo_width(),
                                       row_button.winfo_rooty())
        self.subdropdown.parent_label = item.label

    def _popup(self, items, x, y):
        """A borderless list of `items` at screen position x, y."""
        t = self.theme
        menu = ctk.CTkToplevel(self, fg_color=t["bg_raised"])
        menu.overrideredirect(True)
        menu.grid_columnconfigure(0, weight=1)
        row = 0
        for item in items:
            if item.separator_before and row:
                ctk.CTkFrame(menu, height=1, fg_color=t["line"], corner_radius=0
                             ).grid(row=row, column=0, sticky="ew", padx=6, pady=3)
                row += 1
            tick = "✓  " if item.checked and item.checked() else "    "
            text = tick + item.label + ("  ›" if item.submenu else "")
            row_button = ctk.CTkButton(menu, text=text, anchor="w", width=260, height=30,
                                       corner_radius=0, fg_color="transparent",
                                       hover_color=t["bg_select"], text_color=t["text"],
                                       font=t.ui())
            if item.submenu:
                open_it = lambda b=row_button, i=item: self.open_submenu(b, i)
                row_button.configure(command=open_it)
                row_button.bind("<Enter>", lambda _e, o=open_it: o(), add="+")
            else:
                row_button.configure(command=lambda c=item.command: self._run(c))
                row_button.bind("<Enter>", lambda _e, m=menu: self._leave_submenu(m), add="+")
            row_button.grid(row=row, column=0, sticky="ew")
            row += 1
        # A borderless toplevel is positioned by its window geometry.
        menu.geometry(f"+{x}+{y}")
        if self.place_popup is not None:
            self.place_popup(menu)
        else:
            menu.attributes("-topmost", True)
            menu.lift()
        return menu

    def _leave_submenu(self, menu):
        """The pointer moved onto a plain item of the dropdown: close any open submenu."""
        if menu is self.dropdown:
            self.close_submenu()

    def close_submenu(self):
        if self.subdropdown is not None:
            self.subdropdown.destroy()
            self.subdropdown = None

    def close_dropdown(self):
        self.close_submenu()
        if self.dropdown is not None:
            self.dropdown.destroy()
            self.dropdown = None

    def _run(self, command):
        self.close_dropdown()
        command()

    def _click_outside(self, event):
        if self.dropdown is None:
            return
        widget = event.widget
        popups = [str(m) for m in (self.dropdown, self.subdropdown) if m is not None]
        if isinstance(widget, str) or not any(str(widget).startswith(p) for p in popups):
            # A click on a menu button toggles through open_dropdown; any other click closes.
            if not str(widget).startswith(str(self)):
                self.close_dropdown()
