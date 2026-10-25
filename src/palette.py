"""Palettes: one JSON file of named slots per theme, in `src/palettes/`. This module and
those files are the only places a colour or a font is named. No GUI imports here.

Slots (the contract shared with tickets 05 and 11): bg, bg_panel, bg_raised, bg_select,
line, text, text_dim, text_muted, accent, badge_text, flash, stalled (a Stalled Builder's
Activity, fast-live-board 08), family{one per Family},
font_mono, font_ui, size{text sizes in points}.

A font slot is one family name or a list of candidates, best first: the first installed
one draws, and Tk's own default UI or fixed font comes after the last (`font_family`).
"""

import json
from pathlib import Path

from src.model.effort import FAMILIES

PALETTES_DIR = Path(__file__).resolve().parent / "palettes"
# The launch default (the owner made no pick; ticket 05 named graphite). When its file is
# gone, the first palette by name stands in.
DEFAULT = "graphite"


def palette_names(folder=PALETTES_DIR):
    """Every palette file found, by name, sorted."""
    return sorted(p.stem for p in Path(folder).glob("*.json"))


def default_palette(folder=PALETTES_DIR):
    """The palette used when none is saved: graphite, else the first by name."""
    names = palette_names(folder)
    return DEFAULT if DEFAULT in names or not names else names[0]


def font_family(slot, installed, tk_default):
    """The family a font slot draws with: the slot's first candidate among the `installed`
    families (tkinter.font.families()), else `tk_default`, Tk's own default family for
    the slot. A slot is one family name or a list of them, best first."""
    for family in [slot] if isinstance(slot, str) else slot:
        if family in installed:
            return family
    return tk_default


def load_palette(name, folder=PALETTES_DIR):
    """The palette called `name` as a dict of slots plus its `name`. A name that is None,
    unknown, or whose file is unreadable or short of a slot gives the default palette,
    else the next good palette by name: a bad saved choice never stops the app."""
    names = palette_names(folder)
    default = default_palette(folder)
    for candidate in [name, default] + [n for n in names if n != default]:
        if candidate is None:
            continue
        slots = _read(Path(folder) / f"{candidate}.json")
        if slots is not None:
            slots["name"] = candidate
            return slots
    raise FileNotFoundError(f"no readable palette in {folder}")


COLOUR_SLOTS = ("bg", "bg_panel", "bg_raised", "bg_select", "line", "text", "text_dim",
                "text_muted", "accent", "badge_text", "flash", "stalled")
FONT_SLOTS = ("font_mono", "font_ui")
SIZES = ("table_dense", "table_airy", "detail", "readout", "ui", "section",
         "detail_title", "header_title", "card_title")


def _read(path):
    """The slots in `path`, or None when the file is missing, not JSON, or short of a slot."""
    try:
        slots = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(slots, dict):
        return None
    family, size = slots.get("family"), slots.get("size")
    if not (all(isinstance(slots.get(s), str) and slots.get(s) for s in COLOUR_SLOTS)
            and all(_is_font_slot(slots.get(s)) for s in FONT_SLOTS)
            and isinstance(family, dict) and all(isinstance(family.get(f), str) for f in FAMILIES)
            and isinstance(size, dict) and all(isinstance(size.get(s), int) for s in SIZES)):
        return None
    return slots


def _is_font_slot(value):
    """A family name, or a non-empty list of them."""
    names = [value] if isinstance(value, str) else value
    return isinstance(names, list) and bool(names) and all(
        isinstance(n, str) and n for n in names)
