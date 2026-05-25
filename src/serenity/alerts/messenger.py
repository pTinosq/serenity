"""One-line API for sending a message to the user.

`Messenger.send("Hey")` is the canonical way to ping the user from
anywhere in the codebase. The argument is converted to a string via
`str()`, so you can pass plain strings, `Alert` objects, or anything
that defines `__str__`.

No global state — the dispatcher picks the active channel from
settings on every call, so this Just Works from any module.
"""

from __future__ import annotations

from serenity.alerts.dispatcher import dispatch


class Messenger:
    @staticmethod
    def send(message: object) -> None:
        dispatch(message)
