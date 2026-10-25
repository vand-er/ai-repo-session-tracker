"""A palette made ready for the toolkit: colours by slot name and fonts by size slot.
Views take every colour and font from here, never as literals."""

import tkinter.font as tkfont

import customtkinter as ctk

from src.model.ticket import UNKNOWN
from src.palette import font_family


def _tk_family(named_font):
    """The family behind one of Tk's own named fonts (TkDefaultFont, TkFixedFont): the
    last candidate of every font slot."""
    return tkfont.nametofont(named_font).actual("family")


def blend(c1, c2, t):
    """Mix two #rrggbb colours: t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def appearance(palette):
    """CustomTkinter's appearance mode for a palette: "light" when its `bg` is light,
    else "dark". The Windows title bar follows it."""
    r, g, b = (int(palette["bg"][i:i + 2], 16) for i in (1, 3, 5))
    return "light" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 127.5 else "dark"


class Theme:
    """Built once a Tk root exists (font lookup needs one). Every font a view draws with
    comes from here, made once: `fonts` is a cache the window shares between the themes
    it makes, so a palette with the same fonts as the last hands every view the same
    font objects, and nothing is re-laid out for a font that did not change."""

    def __init__(self, palette, fonts=None):
        self.palette = palette
        self.name = palette.get("name", "")
        installed = set(tkfont.families())
        self.mono_family = font_family(palette["font_mono"], installed, _tk_family("TkFixedFont"))
        self.ui_family = font_family(palette["font_ui"], installed, _tk_family("TkDefaultFont"))
        self._fonts = {} if fonts is None else fonts

    def __getitem__(self, slot):
        """A colour slot: theme["bg_panel"]."""
        return self.palette[slot]

    def family(self, name):
        """The colour of a Family; an unknown Family gets the Unknown colour."""
        families = self.palette["family"]
        return families.get(name, families[UNKNOWN])

    def pt(self, size_slot):
        return self.palette["size"][size_slot]

    # Tk widgets read a positive size as points.
    def tk_mono(self, size_slot="table_airy", weight="normal"):
        return (self.mono_family, self.pt(size_slot), weight)

    # CTkFont sizes are pixels at 100% scaling; CustomTkinter applies DPI scaling itself.
    # Made once per theme: a restyle hands the same fonts to every widget.
    def _ctk(self, family, pt, weight):
        key = ("ctk", family, pt, weight)
        font = self._fonts.get(key)
        if font is None:
            font = self._fonts[key] = ctk.CTkFont(family=family, size=round(pt * 96 / 72),
                                                  weight=weight)
        return font

    def ui(self, size_slot="ui", weight="normal"):
        return self._ctk(self.ui_family, self.pt(size_slot), weight)

    def mono(self, size_slot="readout", weight="normal"):
        return self._ctk(self.mono_family, self.pt(size_slot), weight)

    def ctk_default(self, widget, key):
        """CustomTkinter's theme colour `key` of `widget` for this palette's light or dark
        mode (`appearance`), as one colour."""
        colour = ctk.ThemeManager.theme[widget][key]
        if isinstance(colour, (list, tuple)):
            colour = colour[0 if appearance(self.palette) == "light" else 1]
        return colour

    def font(self, kind, size_slot, weight="normal", scale=1.0):
        """A Tk font for drawing on a canvas, the same as `ui()`/`mono()` give a
        CustomTkinter widget at widget scaling `scale`. `kind` is "ui" or "mono". Made once
        per theme."""
        family = self.mono_family if kind == "mono" else self.ui_family
        return self._tk_font(family, -abs(round(round(self.pt(size_slot) * 96 / 72) * scale)),
                             weight)

    def point_font(self, kind, size_slot, weight="normal"):
        """A Tk font in points, as a plain Tk widget reads `tk_mono`'s description. `kind`
        is "ui" or "mono". Made once."""
        family = self.mono_family if kind == "mono" else self.ui_family
        return self._tk_font(family, self.pt(size_slot), weight)

    def _tk_font(self, family, size, weight):
        key = (family, size, weight)    # size: negative in px, positive in points
        font = self._fonts.get(key)
        if font is None:
            font = self._fonts[key] = tkfont.Font(family=family, size=size, weight=weight)
        return font

    def char_width(self, size_slot="table_airy"):
        """Width in pixels of one monospaced character at this size."""
        return self.point_font("mono", size_slot).measure("0")
