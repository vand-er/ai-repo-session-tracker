"""The one place the app touches CustomTkinter's private parts.

CustomTkinter has no public way to do a few things the Board needs, so this module reaches
into its internals behind small named functions. Nothing else in the app reads a private
attribute of a toolkit object or imports from a package inside `customtkinter`; the guard
`tests/guards/test_toolkit_private.py` holds that. So a CustomTkinter upgrade that renames
an internal breaks here and only here: check each function below against the new version.

    silence_scrollbar_flush(scrollbar, flush)   # CTkScrollbar's private canvas `_canvas`
    engine_part_items(canvas, part)             # DrawEngine's internal "<part>_parts" tags

The guard reads code, not strings, so it cannot see the second: keep every reliance on a
customtkinter internal name here all the same.
"""


def engine_part_items(canvas, part):
    """The items DrawEngine has drawn on `canvas` for one part of a shape (`border`,
    `inner`, `progress`), found by the tag it gives each: `"<part>_parts"`, an internal
    name, not a public API (src/views/shapes.py renames the items once drawn)."""
    return canvas.find_withtag(f"{part}_parts")


def silence_scrollbar_flush(scrollbar, flush):
    """Make `scrollbar`'s redraw call `flush` instead of `update_idletasks`.

    CTkScrollbar's private redraw ends with `update_idletasks` on its private canvas,
    `_canvas`. Shadowing the method on that one canvas leaves every other widget's flush
    alone."""
    scrollbar._canvas.update_idletasks = flush
