"""Clocks: where the controller reads the time. Imports no GUI toolkit.

    clock.now()    # an aware datetime, in local time

A clock is an adapter passed to the controller, like the window's timer and the runner.
`SystemClock` is the app's; tests pass a stand-in whose time they set, so an Activity's
age (07) and Stalled (08) are checked against a known now.
"""

from datetime import datetime


class SystemClock:
    """The machine's clock."""

    def now(self):
        return datetime.now().astimezone()
