"""Palettes: JSON files of named slots in `src/palettes/`, chosen by name (ticket 11)."""

import json
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from src.palette import PALETTES_DIR, default_palette, font_family, load_palette, palette_names

SHIPPED = ["contrast", "ember", "frost", "graphite", "midnight", "onyx", "paper", "plum"]


class DiscoveryTest(unittest.TestCase):
    def test_the_eight_shipped_palettes_are_listed_by_name(self):
        self.assertEqual(palette_names(), SHIPPED)

    def test_graphite_is_the_launch_default(self):
        self.assertEqual(default_palette(), "graphite")

    def test_without_graphite_the_default_is_the_first_by_name(self):
        with palette_folder("paper", "frost", "plum") as folder:
            self.assertEqual(default_palette(folder), "frost")


class LoadTest(unittest.TestCase):
    def test_a_shipped_palette_loads_under_its_name(self):
        palette = load_palette("paper")
        self.assertEqual(palette["name"], "paper")
        self.assertEqual(palette["bg"], "#ececee")

    def test_an_unknown_name_loads_graphite(self):
        self.assertEqual(load_palette("no-such-palette")["name"], "graphite")

    def test_no_saved_name_loads_graphite(self):
        self.assertEqual(load_palette(None)["name"], "graphite")

    def test_a_file_that_is_not_json_loads_graphite(self):
        with palette_folder("graphite", "paper", broken={"plum": "{not json"}) as folder:
            self.assertEqual(load_palette("plum", folder)["name"], "graphite")

    def test_a_file_missing_a_slot_loads_graphite(self):
        paper = json.loads((PALETTES_DIR / "paper.json").read_text(encoding="utf-8"))
        del paper["family"]["Done"]
        with palette_folder("graphite", broken={"paper": json.dumps(paper)}) as folder:
            self.assertEqual(load_palette("paper", folder)["name"], "graphite")

    def test_a_broken_graphite_gives_way_to_the_next_good_palette_by_name(self):
        with palette_folder("paper", "plum", broken={"contrast": "[]", "graphite": ""}) as folder:
            self.assertEqual(load_palette("graphite", folder)["name"], "paper")


class FontCandidatesTest(unittest.TestCase):
    """A font slot names candidates; the first installed wins, then Tk's default."""

    def test_a_list_slot_gives_its_first_installed_candidate(self):
        installed = {"Menlo", "DejaVu Sans Mono", "Courier"}
        self.assertEqual(font_family(["Consolas", "Menlo", "DejaVu Sans Mono"], installed,
                                     "Courier"), "Menlo")

    def test_a_list_slot_with_nothing_installed_gives_tks_default(self):
        self.assertEqual(font_family(["Segoe UI", "Helvetica Neue"], {"Arial", "Cantarell"},
                                     "Cantarell"), "Cantarell")

    def test_a_single_name_slot_gives_that_family_when_installed(self):
        self.assertEqual(font_family("Segoe UI", {"Segoe UI", "Arial"}, "Arial"), "Segoe UI")

    def test_a_palette_with_list_font_slots_loads(self):
        self.assertEqual(self._load_with(["Menlo", "Consolas"], ["Segoe UI", "Cantarell"]),
                         (["Menlo", "Consolas"], ["Segoe UI", "Cantarell"]))

    def test_a_palette_with_single_name_font_slots_still_loads(self):
        self.assertEqual(self._load_with("Consolas", "Segoe UI"), ("Consolas", "Segoe UI"))

    def test_an_empty_or_non_name_font_list_gives_way_to_graphite(self):
        for bad in ([], [""], ["Consolas", 3]):
            with self.subTest(slot=bad):
                with palette_folder("graphite", broken={"paper": self._paper(bad, "Segoe UI")}) as folder:
                    self.assertEqual(load_palette("paper", folder)["name"], "graphite")

    def _load_with(self, mono, ui):
        """Paper with these font slots, loaded from a temp folder: its (font_mono, font_ui)."""
        with palette_folder("graphite", broken={"paper": self._paper(mono, ui)}) as folder:
            palette = load_palette("paper", folder)
        self.assertEqual(palette["name"], "paper")
        return palette["font_mono"], palette["font_ui"]

    @staticmethod
    def _paper(mono, ui):
        paper = json.loads((PALETTES_DIR / "paper.json").read_text(encoding="utf-8"))
        paper["font_mono"], paper["font_ui"] = mono, ui
        return json.dumps(paper)


class ShippedFontsTest(unittest.TestCase):
    """The shipped palettes keep today's Windows look wherever those fonts exist."""

    # Each shipped palette's (font_mono, font_ui) before font slots became lists.
    TODAY = {"contrast": ("Consolas", "Segoe UI"), "ember": ("Consolas", "Segoe UI"),
             "frost": ("Cascadia Mono", "Segoe UI"), "graphite": ("Consolas", "Segoe UI"),
             "midnight": ("Consolas", "Segoe UI"), "onyx": ("Cascadia Mono", "Segoe UI"),
             "paper": ("Consolas", "Segoe UI"), "plum": ("Cascadia Mono", "Segoe UI")}
    WINDOWS = {"Segoe UI", "Consolas", "Cascadia Mono", "Courier New", "Arial"}
    MAC = {"Helvetica Neue", "Menlo", "Monaco", "Courier"}
    LINUX = {"DejaVu Sans", "DejaVu Sans Mono", "Liberation Mono", "Noto Sans"}

    def resolved(self, name, installed):
        palette = load_palette(name)
        return (font_family(palette["font_mono"], installed, "TkFixedFont family"),
                font_family(palette["font_ui"], installed, "TkDefaultFont family"))

    def test_every_shipped_palette_resolves_to_todays_windows_fonts(self):
        installed = self.WINDOWS | self.MAC | self.LINUX
        self.assertEqual(set(self.TODAY), set(SHIPPED))
        for name, today in self.TODAY.items():
            with self.subTest(palette=name):
                self.assertEqual(self.resolved(name, installed), today)

    def test_without_cascadia_mono_windows_falls_back_to_consolas_as_before(self):
        installed = self.WINDOWS - {"Cascadia Mono"}
        for name in SHIPPED:
            with self.subTest(palette=name):
                self.assertEqual(self.resolved(name, installed), ("Consolas", "Segoe UI"))

    def test_on_macos_every_shipped_palette_finds_an_installed_font(self):
        for name in SHIPPED:
            with self.subTest(palette=name):
                mono, ui = self.resolved(name, self.MAC)
                self.assertIn(mono, self.MAC)
                self.assertIn(ui, self.MAC)

    def test_on_linux_every_shipped_palette_finds_an_installed_font(self):
        for name in SHIPPED:
            with self.subTest(palette=name):
                mono, ui = self.resolved(name, self.LINUX)
                self.assertIn(mono, self.LINUX)
                self.assertIn(ui, self.LINUX)


@contextmanager
def palette_folder(*names, broken=()):
    """A temp palettes folder holding copies of the named shipped palettes, plus a file
    per name in `broken` with the given text."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            shutil.copy(PALETTES_DIR / f"{name}.json", Path(tmp) / f"{name}.json")
        for name, text in dict(broken).items():
            (Path(tmp) / f"{name}.json").write_text(text, encoding="utf-8")
        yield Path(tmp)


if __name__ == "__main__":
    unittest.main()
