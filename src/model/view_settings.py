"""The View menu's toggles, kept in the Workspace file by name. No GUI imports."""

DETAIL_PANE = "show_detail_pane"
AREA_COLUMN = "show_area_column"
DEFAULTS = {DETAIL_PANE: True, AREA_COLUMN: False}   # the Area column is off by default


def is_on(workspace, key):
    """The saved toggle, or its default when missing or not a bool."""
    return workspace.setting(key, DEFAULTS[key])


def toggle(workspace, key):
    """Flip the toggle in the Workspace (the caller saves it) and return its new value."""
    workspace.settings[key] = not is_on(workspace, key)
    return workspace.settings[key]
