"""Run the Wayfinder board. `wayfinder-board` and `python -m src` take the same flags.

    wayfinder-board                                 # the default Workspace
    wayfinder-board --workspace C:/tmp/ws.json      # another Workspace file
    wayfinder-board --open FOLDER                   # also open a tab on FOLDER (as File > New tab)
    wayfinder-board --effort NAME                   # show Effort NAME in the fronted tab
    wayfinder-board --select FILE                   # then click FILE's Ticket row
    wayfinder-board --theme NAME                    # then switch to palette NAME live (View > Theme)
    wayfinder-board --sessions                      # open the Sessions tab
    wayfinder-board --menu View                     # then open the View menu
    wayfinder-board --shot out.png                  # draw, save a PNG of the window, quit
                                                    # (on the other monitor, behind, unfocused;
                                                    # gives up, exit 3, after SHOT_LIMIT_S = 20 s)
"""

# The help text stays ASCII: a console on a legacy code page (Windows cp1252) can't print more.
# The app's modules are imported inside main() and the loaders below, after the flags are
# parsed, so `--help` answers on a system where the GUI toolkit can't load yet.

import argparse
import os
import sys
import threading
from datetime import timedelta
from pathlib import Path

from src.clock import SystemClock

STEP_MS = 400        # between the scripted steps, so each one draws before the next
SHOT_LIMIT_S = 20    # --shot gives up when the PNG isn't saved this long after the start
SHOT_FAILED = 3      # --shot's exit code when it gives up
WATCH_POLL_S = 0.1   # how often the watchdog reads the clock
CLOCK = SystemClock()
_exit = os._exit     # ends the process from any thread, whatever the UI thread is doing


def build_app(workspace_file=None):
    """The window and its controller (`src.app.build_app`), loaded only when called."""
    from src import app
    return app.build_app(workspace_file)


# Windows-only dev tools: loaded only for a scripted still, never on a normal start.

def guard_foreground():
    """`src.views.placement.guard_foreground`, loaded only when called."""
    from src.views import placement
    placement.guard_foreground()


def keep_behind(window, workspace=None, move=True):
    """`src.views.placement.keep_behind`, loaded only when called."""
    from src.views import placement
    placement.keep_behind(window, workspace, move=move)


def shoot(window, out_path, **options):
    """`src.views.screenshot.shoot`, loaded only when called."""
    from src.views import screenshot
    return screenshot.shoot(window, out_path, **options)


def start_watchdog(message):
    """A thread that, unless the returned event is set first, prints `message` and ends
    the process SHOT_LIMIT_S after now. It runs off the UI thread, so a window stuck in a
    callback (or never drawing at all) still ends."""
    stop = threading.Event()
    deadline = CLOCK.now() + timedelta(seconds=SHOT_LIMIT_S)

    def watch():
        while not stop.wait(WATCH_POLL_S):
            if CLOCK.now() >= deadline:
                print(message, file=sys.stderr, flush=True)
                sys.stdout.flush()
                _exit(SHOT_FAILED)
                return
    threading.Thread(target=watch, daemon=True, name="shot-watchdog").start()
    return stop


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wayfinder-board", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", help="Workspace file to load and save (default: the owner's)")
    parser.add_argument("--open", metavar="FOLDER", help="open a tab on this Source folder")
    parser.add_argument("--effort", metavar="NAME", help="show this Effort in the fronted tab")
    parser.add_argument("--select", metavar="FILE", help="click this Ticket's row in the fronted tab")
    parser.add_argument("--theme", metavar="NAME", help="switch to this palette live, after --select")
    parser.add_argument("--shot", metavar="PNG",
                        help="save a PNG of the window, then quit; if it isn't saved within "
                             f"{SHOT_LIMIT_S} s (SHOT_LIMIT_S), exit {SHOT_FAILED} with a message")
    parser.add_argument("--sessions", action="store_true",
                        help="open the Sessions tab (as View > Sessions)")
    parser.add_argument("--menu", metavar="NAME",
                        help="open this menu of the menu bar last, so --shot shows it open")
    args = parser.parse_args(argv)
    if args.menu is not None:
        from src.views.options_bar import MENU_ORDER   # a GUI module: only once --menu is given
        menu = next((m for m in MENU_ORDER if m.lower() == args.menu.lower()), None)
        if menu is None:
            parser.error(f"--menu: no menu {args.menu!r}; the menus are {', '.join(MENU_ORDER)}")
        args.menu = menu

    watchdog = None
    if args.shot:
        watchdog = start_watchdog(
            f"--shot: the window did not draw and save {args.shot} within {SHOT_LIMIT_S} s; "
            "giving up")
        guard_foreground()
    window, controller = build_app(args.workspace)
    if args.shot:
        # A scripted still opens away from the owner: other monitor, behind, never focused.
        keep_behind(window, controller.workspace)
        window.options_bar.place_popup = lambda popup: keep_behind(popup, move=False)
    if args.open:
        controller.new_tab(args.open)
    if args.effort and controller.front_tab() is not None:
        controller.select_effort(controller.front_tab(), args.effort)
    if args.sessions:
        controller.open_sessions()
    steps = []
    if args.select:
        steps.append(lambda: controller.front_tab() and
                     controller.front_tab().view.select_row(Path(args.select).resolve()))
    if args.theme:
        steps.append(lambda: controller.set_palette(args.theme))
    if args.menu:
        steps.append(lambda: window.options_bar.open_menu(args.menu))
    if args.shot:
        bar = window.options_bar
        steps.append(lambda: shoot(window, args.shot, done=controller.quit,
                                   also=bar.open_popups))
    for n, step in enumerate(steps, start=1):
        window.after(n * STEP_MS + 400, step)
    window.mainloop()
    if watchdog is not None:
        watchdog.set()


if __name__ == "__main__":
    main()
