"""CustomTkinter's rounded shapes on one canvas (src/views/shapes.py), through Shapes'
own calls on a real canvas: a shape drawn again the same is not drawn anew, a moved
shape keeps its items, colours reach every part, and a hidden shape is coloured when
it shows. These are what keep a redraw within the 20 ms bar."""

import tkinter as tk
import unittest

import customtkinter as ctk

from src.views.shapes import Items, Shapes


class ShapesTest(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.canvas = ctk.CTkCanvas(self.root, width=200, height=200)
        self.shapes = Shapes(self.canvas)

    def items(self, tag):
        return set(self.canvas.find_withtag(tag))

    def fills(self, tag):
        return {self.canvas.itemcget(item, "fill") for item in self.canvas.find_withtag(tag)}

    def test_a_new_shape_draws_items_and_asks_for_a_restack(self):
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        self.assertTrue(self.items("card"))
        self.assertTrue(self.shapes.restack)

    def test_the_same_shape_again_draws_nothing_new(self):
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        drawn, everything = self.items("card"), set(self.canvas.find_all())
        self.shapes.restack = False
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        self.assertEqual(self.items("card"), drawn)
        self.assertEqual(set(self.canvas.find_all()), everything)
        self.assertFalse(self.shapes.restack)

    def test_a_moved_shape_keeps_its_items_and_moves_them(self):
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        drawn, box = self.items("card"), self.canvas.bbox("card")
        self.shapes.restack = False
        self.shapes.rounded_rect("card", 30, 50, 100, 60, radius=8)
        self.assertEqual(self.items("card"), drawn)
        self.assertEqual(self.canvas.bbox("card"),
                         (box[0] + 20, box[1] + 40, box[2] + 20, box[3] + 40))
        self.assertFalse(self.shapes.restack)

    def test_a_resized_shape_reuses_its_items(self):
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        count = len(self.canvas.find_all())
        self.shapes.rounded_rect("card", 10, 10, 140, 90, radius=8)
        self.assertEqual(len(self.canvas.find_all()), count)

    def test_a_colour_reaches_every_part_and_a_redrawn_shape_keeps_it(self):
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        self.shapes.colour("card", inner="#252933")
        self.assertEqual(self.fills("card.inner"), {"#252933"})
        self.shapes.rounded_rect("card", 10, 10, 140, 90, radius=8)
        self.assertEqual(self.fills("card.inner"), {"#252933"})

    def test_a_hidden_shape_is_coloured_when_it_shows(self):
        self.shapes.rounded_rect("card", 10, 10, 100, 60, radius=8)
        self.shapes.colour("card", inner="#000000")
        self.shapes.show("card", False)
        self.shapes.colour("card", inner="#ffffff")
        self.assertEqual(self.fills("card.inner"), {"#000000"})   # not yet: it is hidden
        self.shapes.show("card", True)
        self.assertEqual(self.fills("card.inner"), {"#ffffff"})
        self.assertEqual({self.canvas.itemcget(i, "state") for i in self.items("card")},
                         {"normal"})


class ItemsTest(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.canvas = tk.Canvas(self.root)
        self.items = Items(self.canvas)

    def test_put_sets_coords_and_options(self):
        item = self.items.add(self.canvas.create_text(0, 0, text="a"), text="a")
        self.items.put(item, (5, 7), text="b", fill="#123456")
        self.assertEqual(self.canvas.coords(item), [5.0, 7.0])
        self.assertEqual(self.canvas.itemcget(item, "text"), "b")
        self.assertEqual(self.canvas.itemcget(item, "fill"), "#123456")

    def test_put_leaves_an_option_it_already_set(self):
        item = self.items.add(self.canvas.create_text(0, 0, text="a"), text="a")
        self.items.put(item, text="b")
        self.canvas.itemconfigure(item, text="changed behind its back")
        self.items.put(item, text="b")     # "b" is what it last set: no Tk call
        self.assertEqual(self.canvas.itemcget(item, "text"), "changed behind its back")


if __name__ == "__main__":
    unittest.main()
