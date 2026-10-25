"""The Protocol conformance guard: the real views and the test fakes satisfy the view
Protocols in `src/view_protocols.py`.

It checks member names and, for methods, arity: every call the Protocol allows must bind
on the implementation (how many positional arguments, and the names of any the controller
passes by keyword). `runtime_checkable` alone would check names only. The fakes are
checked here; the real views import a GUI toolkit, so they are checked in a fresh
interpreter and the hook's process never imports one."""

import unittest

from src.view_protocols import BoardViewProtocol, MainWindowProtocol, SessionsViewProtocol
from tests.fakes import FakeBoard, FakeSessions, FakeWindow
from tests.guards.protocols import protocol_gaps, real_view_check, start_real_view_check
from tests.guards.tree import fresh_check, fresh_started

# Registered, not started: the first guard to need a fresh interpreter starts them all
# side by side (`fresh_started`), and the hook must stay fast.
fresh_check("real views", start_real_view_check)


class RealViewsTest(unittest.TestCase):
    """In the fresh interpreter: the full suite imports the views in this process."""

    @classmethod
    def setUpClass(cls):
        cls.result = real_view_check(fresh_started("real views"))

    def test_the_real_window_board_and_sessions_views_satisfy_their_protocols(self):
        self.assertEqual(self.result["gaps"], [])

    def test_this_guard_imports_no_gui_toolkit_until_it_imports_the_views(self):
        self.assertEqual(self.result["toolkits"], [])


class FakesTest(unittest.TestCase):
    def test_the_fake_window_satisfies_the_main_window_protocol(self):
        self.assertEqual(protocol_gaps(FakeWindow, MainWindowProtocol), [])

    def test_the_fake_board_satisfies_the_board_view_protocol(self):
        self.assertEqual(protocol_gaps(FakeBoard, BoardViewProtocol), [])

    def test_the_fake_sessions_view_satisfies_the_sessions_view_protocol(self):
        self.assertEqual(protocol_gaps(FakeSessions, SessionsViewProtocol), [])


class PlantedTest(unittest.TestCase):
    """Planted on temp classes: a copy of a fake with one member taken away or changed."""

    @staticmethod
    def _copy(cls, **changes):
        members = {k: v for k, v in vars(cls).items() if k not in ("__dict__", "__weakref__")}
        members.update(changes)
        return type(f"Planted{cls.__name__}", (), {k: v for k, v in members.items()
                                                    if v is not None})

    def test_a_fake_lacking_a_protocol_method_fails_naming_it(self):
        planted = self._copy(FakeWindow, ask_folder=None)
        gaps = protocol_gaps(planted, MainWindowProtocol)
        self.assertEqual(len(gaps), 1)
        self.assertIn("ask_folder", gaps[0])
        self.assertIn("PlantedFakeWindow", gaps[0])

    def test_a_fake_lacking_a_settable_callback_fails_naming_it(self):
        planted = self._copy(FakeBoard, __init__=lambda self: None)
        gaps = " ".join(protocol_gaps(planted, BoardViewProtocol))
        for name in ("on_sort", "on_activity", "on_builder"):
            self.assertIn(name, gaps)

    def test_a_fake_method_taking_too_few_arguments_fails_naming_it(self):
        planted = self._copy(FakeSessions, show=lambda self, rows, caption: None)
        gaps = protocol_gaps(planted, SessionsViewProtocol)
        self.assertEqual(len(gaps), 1)
        self.assertIn("show", gaps[0])

    def test_a_fake_method_needing_more_arguments_fails_naming_it(self):
        planted = self._copy(FakeBoard, flash=lambda self, paths, colour: None)
        gaps = protocol_gaps(planted, BoardViewProtocol)
        self.assertEqual(len(gaps), 1)
        self.assertIn("flash", gaps[0])

    def test_a_keyword_the_controller_passes_must_be_accepted_by_name(self):
        planted = self._copy(FakeBoard, show_activity=lambda self, activity, frozen=(): None)
        gaps = protocol_gaps(planted, BoardViewProtocol)
        self.assertEqual(len(gaps), 1)
        self.assertIn("stalled", gaps[0])


if __name__ == "__main__":
    unittest.main()
