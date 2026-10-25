"""Reading folders and files the cheap way, for every scan. Pure: imports no GUI.

    entry_stats(folder, "*.md")     # {name: stat or None}, one directory read
    lines, whole = tail_lines(open_file, 64 * 1024)
"""

import fnmatch
import os


def entry_stats(folder, pattern=None):
    """`{name: os.stat_result or None}` for each entry of `folder` whose name matches
    `pattern` (fnmatch; None for every entry), from the folder's directory entries,
    which carry their stat on Windows: no file is opened or statted one by one. None
    for an entry gone before it could be statted. Raises OSError when `folder` cannot
    be listed."""
    found = {}
    with os.scandir(folder) as entries:
        for entry in entries:
            if pattern is None or fnmatch.fnmatch(entry.name, pattern):
                try:
                    found[entry.name] = entry.stat()
                except OSError:
                    found[entry.name] = None
    return found


def tail_lines(file, nbytes):
    """`(lines, whole)`: the lines in the last `nbytes` of the open binary `file`, and
    whether they start at its beginning. The first line, cut mid-way by the start of the
    read, is dropped."""
    size = file.seek(0, 2)
    start = max(0, size - nbytes)
    file.seek(start)
    lines = file.read(size - start).splitlines()
    return (lines[1:] if start > 0 else lines), start == 0
