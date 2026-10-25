"""Composition: build the window and the controller, and register the options-bar menus.

Each menu area registers its own items. A later ticket adds a `register_*` function (in
its own module if it likes) and one entry in MENU_REGISTRARS; menus are drawn in the
order File, View, Actions, Help whatever order items are registered in.
"""

from src.actions import register_actions_menu
from src.controller import BoardController, restore_palette
from src.model.view_settings import AREA_COLUMN, DETAIL_PANE
from src.palette import palette_names
from src.runner import BackgroundRunner
from src.views.about import show_about
from src.views.options_bar import MenuItem
from src.views.window import MainWindow
from src.workspace import load_workspace, workspace_path

NAME = "Wayfinder board"
VERSION = "0.6.0"


def register_file_menu(bar, controller, window):
    bar.add_item("File", "New tab…", controller.new_tab)
    bar.add_item("File", "Close tab", controller.close_tab)
    bar.add_item("File", "Reopen last", controller.reopen_last)
    bar.add_item("File", "Quit", controller.quit, separator_before=True)


def register_theme_menu(bar, controller, window):
    """View → Theme: a submenu listing every palette file found, by name, the current one
    ticked. Choosing one restyles the window at once and saves the choice."""
    def themes():
        return [MenuItem(name, lambda n=name: controller.set_palette(n),
                         checked=lambda n=name: controller.workspace.palette == n)
                for name in palette_names()]
    bar.add_submenu("View", "Theme", themes)


def register_view_toggles(bar, controller, window):
    """View → Show detail pane, Show Area column (saved in the Workspace), Refresh now."""
    bar.add_item("View", "Show detail pane", lambda: controller.toggle_view(DETAIL_PANE),
                 checked=lambda: controller.view_on(DETAIL_PANE), separator_before=True)
    bar.add_item("View", "Show Area column", lambda: controller.toggle_view(AREA_COLUMN),
                 checked=lambda: controller.view_on(AREA_COLUMN))
    bar.add_item("View", "Refresh now", controller.refresh_now, separator_before=True)


def register_help_menu(bar, controller, window):
    bar.add_item("Help", "About", lambda: show_about(window, NAME, VERSION))


def register_sessions_menu(bar, controller, window):
    """View → Sessions opens the one Sessions tab, or fronts it."""
    bar.add_item("View", "Sessions", controller.open_sessions, separator_before=True)


MENU_REGISTRARS = (register_file_menu, register_theme_menu, register_view_toggles,
                   register_sessions_menu, register_actions_menu, register_help_menu)


def build_app(workspace_file=None):
    """The window and its controller, with the saved tabs reopened. Call mainloop() on
    the window to run it."""
    path = workspace_path(workspace_file)
    workspace = load_workspace(path)
    window = MainWindow(restore_palette(workspace))
    controller = BoardController(workspace, path, window, runner=BackgroundRunner(window.after))
    window.controller = controller
    for register in MENU_REGISTRARS:
        register(window.options_bar, controller, window)
    controller.start()
    return window, controller
