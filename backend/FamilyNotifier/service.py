from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class NumberNotifier(Protocol):
    async def notify(self, to_number: str, message: str) -> None:
        """Send a notification to the provided phone number."""


@dataclass
class FamilyNotifierService:
    """
    Broadcast pre-defined alert messages to a list of family contacts.

    The service is intentionally lightweight: it depends on a notifier that
    knows how to deliver a message to a single phone number.  When invoked, it
    formats a stored message template and forwards it to every registered
    contact concurrently.
    """

    notifier: NumberNotifier
    numbers: Sequence[str]
    messages: Mapping[str, str]

    async def notify(self, message_key: str, context: Mapping[str, Any] | None = None) -> None:
        """
        Send the message identified by `message_key` to all configured numbers.

        :param message_key: Key of the template in `messages`.
        :param context: Optional values interpolated into the template via
                        `str.format(**context)`.
        :raises ValueError: If the message key is unknown.
        """
        try:
            template = self.messages[message_key]
        except KeyError as exc:
            raise ValueError(f"Unknown family notification message: {message_key}") from exc

        payload = template.format(**(context or {}))
        if not self.numbers:
            return

        await asyncio.gather(*(self.notifier.notify(number, payload) for number in self.numbers))
