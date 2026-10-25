"""The colour and font guard: a hex colour or a font name is written only in the palette
loader (`src/palette.py`) and the palette files (`src/palettes/`), so each is a slot."""

import unittest

from tests.guards.literals import colour_font_violations, palette_fonts
from tests.guards.planted import REPO, planted_tree


class ColourFontGuardTest(unittest.TestCase):
    def test_no_colour_or_font_is_named_outside_the_palettes(self):
        self.assertEqual(colour_font_violations(REPO), [])

    def test_the_font_names_checked_are_the_ones_the_palettes_use(self):
        # A slot is one family or a list of candidates (src/palette.py); every one counts.
        self.assertEqual(palette_fonts(REPO), {
            "Cantarell", "Cascadia Mono", "Consolas", "DejaVu Sans", "DejaVu Sans Mono",
            "Helvetica Neue", "Liberation Mono", "Liberation Sans", "Menlo", "Monaco",
            "Noto Sans", "Noto Sans Mono", "Segoe UI"})

    def test_a_planted_hex_colour_fails_naming_it(self):
        planted = "def paint(label):\n    label.configure(fg_color='#1a2742')\n"
        with planted_tree({"src/views/planted.py": planted}) as root:
            violations = colour_font_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.views.planted line 2", violations[0])
        self.assertIn("#1a2742", violations[0])

    def test_a_planted_font_name_fails_naming_it(self):
        planted = "FONT = ('Segoe UI', 12)\n"
        with planted_tree({"src/views/planted.py": planted}) as root:
            violations = colour_font_violations(root)
        self.assertEqual(len(violations), 1)
        self.assertIn("src.views.planted line 1", violations[0])
        self.assertIn("Segoe UI", violations[0])

    def test_the_palette_loader_may_name_fonts(self):
        planted = "MONO_FALLBACKS = ('Consolas', 'Courier New')\nACCENT = '#38bdf8'\n"
        with planted_tree({"src/palette.py": planted}) as root:
            self.assertEqual(colour_font_violations(root), [])
