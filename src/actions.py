"""The Actions menu: Open in Explorer and Open in editor, for the fronted tab's selected
file (a Ticket, Map or Spec). Imports no GUI toolkit; how each system reveals and opens a
file lives in `src.system`."""

from src import system


def _on_selected(controller, action):
    tab = controller.front_tab()
    if tab is not None and tab.selected is not None:
        action(tab.selected)


def register_actions_menu(bar, controller, window):
    bar.add_item("Actions", "Open in Explorer",
                 lambda: _on_selected(controller, system.reveal))
    bar.add_item("Actions", "Open in editor",
                 lambda: _on_selected(controller, system.open_in_editor))
