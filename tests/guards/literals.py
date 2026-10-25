"""The literal rules, read from a tree's source. Each returns one line per violation, naming
the module, the line and what it found; an empty list means the rule holds.

Only the app (`src/`) is checked: the tests and the tools are exempt. Modules are found by
walking the package (`app_modules`), so a new module is checked without anyone listing it.
"""

import ast
import json
import re

from tests.guards.tree import APP, app_modules, source, tree

LAYOUT_CALLS = ("place", "pack")


def _tree(root, name):
    return tree(root).parse(source(root, name))


def layout_violations(root):
    """Every `.place(` or `.pack(` call in the app: layout stays on the grid."""
    found = []
    for name in app_modules(root):
        for node in ast.walk(_tree(root, name)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in LAYOUT_CALLS):
                found.append(f"{name} line {node.lineno}: .{node.func.attr}( (lay out on the grid)")
    return found


PALETTE_LOADER = "src.palette"
PALETTES = "palettes"
FONT_SLOTS = ("font_mono", "font_ui")
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,12}\b")


def palette_fonts(root):
    """The font names the palette files use: the names the colour and font rule checks. A
    slot holds one family name or a list of candidates, best first; every candidate counts."""
    fonts = set()
    for path in tree(root).paths(f"{APP}/{PALETTES}", ".json", recursive=False):
        slots = json.loads(tree(root).text(path))
        for slot in FONT_SLOTS:
            value = slots.get(slot)
            if isinstance(value, str):
                fonts.add(value)
            elif isinstance(value, list):
                fonts.update(value)
    return fonts


def _strings(root, name):
    """`(line, text)` of every string written in the module, docstrings and f-string parts
    included. Comments are not strings, so a comment may still name a font."""
    for node in ast.walk(_tree(root, name)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def colour_font_violations(root):
    """Every hex colour or palette font name written outside the palette loader."""
    fonts = sorted(palette_fonts(root))
    found = []
    for name in app_modules(root):
        if name == PALETTE_LOADER:
            continue
        for line, text in _strings(root, name):
            for match in HEX_COLOUR.finditer(text):
                at = line + text.count("\n", 0, match.start())
                found.append(f"{name} line {at}: colour {match.group()} (use a palette slot)")
            for font in fonts:
                if font in text:
                    at = line + text.count("\n", 0, text.index(font))
                    found.append(f"{name} line {at}: font {font!r} (use font_mono or font_ui)")
    return found


TICKET_MODULE = "src.model.ticket"


def family_names(root):
    """The Families the Ticket module defines: the strings it binds to upper-case names at
    module level (`DONE = "Done"`, `NEEDS_ME, ACTIVE = "Needs me", "Active"`)."""
    names = set()
    for node in _tree(root, TICKET_MODULE).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            pairs = (zip(target.elts, node.value.elts)
                     if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple)
                     else [(target, node.value)])
            for bound, value in pairs:
                if (isinstance(bound, ast.Name) and bound.id.isupper()
                        and isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    names.add(value.value)
    return names


def family_violations(root):
    """Every string that is exactly a Family's name, written outside the Ticket module."""
    families = family_names(root)
    found = []
    for name in app_modules(root):
        if name == TICKET_MODULE:
            continue
        for line, text in _strings(root, name):
            if text in families:
                found.append(f"{name} line {line}: Family {text!r} "
                             f"(import it from {TICKET_MODULE})")
    return found
