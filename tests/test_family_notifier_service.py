import asyncio

import pytest

from backend.FamilyNotifier.service import FamilyNotifierService


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent = []

    async def notify(self, to_number: str, message: str) -> None:
        self.sent.append((to_number, message))


def test_family_notifier_delivers_messages_to_all_contacts() -> None:
    recorder = RecordingNotifier()
    service = FamilyNotifierService(
        notifier=recorder,
        numbers=["+111", "+222"],
        messages={"alert": "Hello {name}, code {code}!"},
    )

    async def exercise():
        await service.notify("alert", {"name": "Ana", "code": "XYZ"})

    asyncio.run(exercise())

    assert sorted(recorder.sent) == [
        ("+111", "Hello Ana, code XYZ!"),
        ("+222", "Hello Ana, code XYZ!"),
    ]


def test_family_notifier_raises_for_unknown_message_key() -> None:
    recorder = RecordingNotifier()
    service = FamilyNotifierService(
        notifier=recorder, numbers=["+111"], messages={"alert": "Hi"}
    )

    async def exercise():
        await service.notify("missing")

    with pytest.raises(ValueError):
        asyncio.run(exercise())
