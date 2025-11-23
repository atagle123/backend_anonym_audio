from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from backend.Notifier.service import TwilioClient

from .audio_flag_service import FlaggedTranscript


class NotificationService(Protocol):
    async def notify_flagged(self, transcript: FlaggedTranscript) -> None:
        """Trigger alerts when a transcript segment is flagged."""


@dataclass
class TwilioNotifier:
    """
    Send voice + SMS + WhatsApp alerts using Twilio when scammy content is detected.

    The notifier runs the Twilio SDK blocking calls inside thread executors so
    that we do not block the event loop.
    """

    twilio: TwilioClient
    phone_target: str
    whatsapp_target: str
    twiml_url: str
    message_template: str = "Se detectó un posible fraude: {text}"

    async def notify_flagged(self, transcript: FlaggedTranscript) -> None:
        payload = self.message_template.format(text=transcript.text)
        tasks = [
            asyncio.to_thread(
                self.twilio.create_call, self.phone_target, self.twiml_url
            ),
            asyncio.to_thread(self.twilio.send_sms, self.phone_target, payload),
        ]
        tasks.append(
            asyncio.to_thread(self.twilio.send_whatsapp, self.whatsapp_target, payload)
        )
        await asyncio.gather(*tasks)
