"""Every shipped palette file has exactly the contract's slots (tickets 05 and 11;
progress.md palette contract). Runs against the app's own `src/palettes/`."""

import json
import re
import unittest

from src.model.ticket import STATUS_FAMILY, UNKNOWN
from src.palette import PALETTES_DIR as PALETTE_DIR
from src.palette import load_palette

COLOUR_SLOTS = {"bg", "bg_panel", "bg_raised", "bg_select", "line", "text", "text_dim",
                "text_muted", "accent", "flash", "badge_text",
                "stalled"}   # a Stalled Builder's Activity text (fast-live-board 08)
FONT_SLOTS = {"font_mono", "font_ui"}
SLOTS = COLOUR_SLOTS | FONT_SLOTS | {"family", "size"}
# Finished is no Status's Family: only a Ticket's mark reaches it (fast-live-board 05).
FAMILIES = set(STATUS_FAMILY.values()) | {UNKNOWN, "Finished"}
SIZES = {"table_dense", "table_airy", "detail", "readout", "ui", "section",
         "detail_title", "header_title", "card_title"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def palettes():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(PALETTE_DIR.glob("*.json"))}


class PaletteSlotTest(unittest.TestCase):
    def test_the_eight_shipped_palettes_are_there(self):
        # At least these eight: the README tells the owner to add more files beside them.
        shipped = {"contrast", "ember", "frost", "graphite", "midnight", "onyx", "paper", "plum"}
        self.assertLessEqual(shipped, set(palettes()))

    def test_every_palette_has_exactly_the_slots(self):
        for name, p in palettes().items():
            with self.subTest(palette=name):
                self.assertEqual(set(p), SLOTS)
                self.assertEqual(set(p["family"]), FAMILIES)
                self.assertEqual(set(p["size"]), SIZES)

    def test_colours_are_hex_and_fonts_are_names(self):
        for name, p in palettes().items():
            for slot in COLOUR_SLOTS:
                with self.subTest(palette=name, slot=slot):
                    self.assertRegex(p.get(slot, ""), HEX)
            for fam, colour in p.get("family", {}).items():
                with self.subTest(palette=name, family=fam):
                    self.assertRegex(colour, HEX)
            for slot in FONT_SLOTS:
                with self.subTest(palette=name, slot=slot):
                    # One family name, or a list of candidates, best first (open-source-release 04).
                    value = p.get(slot)
                    names = [value] if isinstance(value, str) else value
                    self.assertIsInstance(names, list)
                    self.assertTrue(names)
                    for family in names:
                        self.assertIsInstance(family, str)
                        self.assertTrue(family)

    def test_the_app_loads_every_shipped_palette_as_itself(self):
        for name in palettes():
            with self.subTest(palette=name):
                self.assertEqual(load_palette(name)["name"], name)


if __name__ == "__main__":
    unittest.main()
