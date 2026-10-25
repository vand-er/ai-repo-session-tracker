"""Text cut to a cell's width, the one way every table cuts it: to `width` characters,
the last of them an ellipsis.

    cut("What the project rules keep", 12)          # "What the pr…"
    cut_activity(activity, 16)                      # "Running t… · 4s": keeps the age
"""

ELLIPSIS = "…"


def cut(text, width):
    """`text`, or as much of it as fits in `width` characters with an ellipsis."""
    return text if len(text) <= width else text[:max(0, width - 1)] + ELLIPSIS


def cut_activity(activity, width):
    """An ActivityText (`src/model/builders.py`) cut to `width`: its words are cut and its
    age kept, so a narrow row still says how long ago. None gives ""."""
    if not activity:
        return ""
    if len(activity) <= width or not activity.age:
        return cut(activity, width)
    tail = activity[len(activity.words):]          # " · 4s"
    return activity.words[:max(0, width - len(tail) - 1)] + ELLIPSIS + tail
