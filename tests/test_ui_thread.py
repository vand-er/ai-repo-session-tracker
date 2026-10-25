"""Tcl is called only from the UI thread, even when the background runner's thread is the
one that drops the last reference to a font, a variable or an image (as its garbage
collection can): the Tcl clean-up waits for the UI thread to run it.

Uses a real Tcl interpreter: a withdrawn root window, never shown. tkinter is imported
in setUp, not at discovery, so tests that check no GUI was loaded still see none."""

import threading
import unittest

tkinter = None


def font_exists(root, name):
    return name in root.tk.splitlist(root.tk.call("font", "names"))


def variable_exists(root, name):
    return root.tk.getboolean(root.tk.call("info", "exists", name))


def image_exists(root, name):
    return name in root.tk.splitlist(root.tk.call("image", "names"))


class FinalizeOnUiThreadTest(unittest.TestCase):
    def setUp(self):
        global tkinter, run_pending
        import tkinter
        import tkinter.font
        from src.views.ui_thread import finalize_on_ui_thread, run_pending
        self.root = tkinter.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        finalize_on_ui_thread()

    def drop_on_another_thread(self, holder):
        thread = threading.Thread(target=holder.clear, daemon=True)
        thread.start()
        thread.join(5)
        self.assertFalse(thread.is_alive(), "the other thread got stuck calling Tcl")

    def check(self, make, exists):
        thing = make()
        name = str(thing.name) if hasattr(thing, "name") else str(thing)
        holder = [thing]
        del thing
        self.drop_on_another_thread(holder)
        self.assertTrue(exists(self.root, name))     # left for the UI thread
        run_pending()
        self.assertFalse(exists(self.root, name))

    def test_a_font_dropped_off_the_ui_thread_is_deleted_on_it(self):
        self.check(lambda: tkinter.font.Font(root=self.root, family="Arial", size=9),
                   font_exists)

    def test_a_variable_dropped_off_the_ui_thread_is_unset_on_it(self):
        self.check(lambda: tkinter.StringVar(self.root, value="x"), variable_exists)

    def test_an_image_dropped_off_the_ui_thread_is_deleted_on_it(self):
        self.check(lambda: tkinter.PhotoImage(master=self.root, width=2, height=2),
                   image_exists)

    def test_on_the_ui_thread_a_font_is_deleted_at_once(self):
        font = tkinter.font.Font(root=self.root, family="Arial", size=9)
        name = font.name
        del font
        self.assertFalse(font_exists(self.root, name))


if __name__ == "__main__":
    unittest.main()
