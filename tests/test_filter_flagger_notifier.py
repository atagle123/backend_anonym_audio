import asyncio
from typing import AsyncIterable, List

import pytest

from backend.FilterService.chileFilter import ChileScamFilter
from backend.FilterService.filter import FilterService
from backend.FilterService.userFilter import UserFilter
from backend.services.audio_flag_service import AudioFlagService, FlaggedTranscript
from backend.services.notification import TwilioNotifier
from backend.services.speech_to_text import TranscriptSegment


class FakeSpeechToTextService:
    """Simple speech-to-text stub that yields predetermined transcript segments."""

    def __init__(self, segments: List[TranscriptSegment]) -> None:
        self._segments = segments

    async def stream_transcribe(
        self, audio_chunks: AsyncIterable[bytes]
    ) -> AsyncIterable[TranscriptSegment]:
        for segment in self._segments:
            yield segment


class RecordingTwilioClient:
    """Captures outgoing calls and messages for assertions."""

    def __init__(self) -> None:
        self.calls = []
        self.sms = []
        self.whatsapp = []

    def create_call(self, to_number: str, twiml_url: str) -> str:
        self.calls.append((to_number, twiml_url))
        return "call-sid"

    def send_sms(self, to_number: str, message: str) -> str:
        self.sms.append((to_number, message))
        return "sms-sid"

    def send_whatsapp(self, to_number: str, message: str) -> str:
        self.whatsapp.append((to_number, message))
        return "wa-sid"


def test_filter_service_apply_replaces_keywords() -> None:
    base_filter = FilterService(patterns=[r"secret"])
    assert base_filter.filter("This contains a secret code")
    redacted = base_filter.apply("secret secret", replacement="[redacted]")
    assert redacted == "[redacted] [redacted]"


def test_chile_scam_filter_matches_common_keywords() -> None:
    chile_filter = ChileScamFilter()
    assert chile_filter.filter("Necesitamos validar tu clave dinámica ahora mismo")
    assert not chile_filter.filter("Conversación inocua sin alertas")


def test_user_filter_detects_sensitive_user_information() -> None:
    user_filter = UserFilter()
    assert user_filter.filter("Mi clave es 1234 y el token llegó al correo")
    assert not user_filter.filter("Solo conversamos del clima hoy")


def test_audio_flag_service_flags_user_role_segments() -> None:
    stt = FakeSpeechToTextService(
        [TranscriptSegment(text="Necesito tu clave dinámica", is_final=True)]
    )
    service = AudioFlagService(
        speech_to_text=stt,
        filter_service_user=ChileScamFilter(),
        filter_service_scammer=UserFilter(),
    )

    async def collect():
        async def audio_stream():
            yield b"\x00\x01"

        return [
            flagged
            async for flagged in service.process_stream(audio_stream(), role="user")
        ]

    results = asyncio.run(collect())
    assert len(results) == 1
    assert results[0].flagged is True
    assert results[0].text == "Necesito tu clave dinámica"
    assert results[0].is_final is True


def test_audio_flag_service_defaults_to_scammer_filter_for_unknown_roles() -> None:
    stt = FakeSpeechToTextService(
        [TranscriptSegment(text="Mi clave es 5678", is_final=False)]
    )
    service = AudioFlagService(
        speech_to_text=stt,
        filter_service_user=ChileScamFilter(),
        filter_service_scammer=UserFilter(),
    )

    async def collect():
        async def audio_stream():
            yield b"\x02\x03"

        return [
            flagged
            async for flagged in service.process_stream(audio_stream(), role="mystery")
        ]

    results = asyncio.run(collect())
    assert len(results) == 1
    assert results[0].flagged is True
    assert results[0].text == "Mi clave es 5678"


def test_twilio_notifier_triggers_all_channels(monkeypatch) -> None:
    twilio = RecordingTwilioClient()
    notifier = TwilioNotifier(
        twilio=twilio,
        phone_target="+56911111111",
        whatsapp_target="+56922222222",
        twiml_url="https://example.com/twiml",
        message_template="Alerta: {text}",
    )

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.services.notification.asyncio.to_thread", fake_to_thread
    )

    transcript = FlaggedTranscript(
        text="Posible fraude detectado", flagged=True, is_final=True
    )

    async def exercise():
        await notifier.notify_flagged(transcript)

    asyncio.run(exercise())

    assert twilio.calls == [("+56911111111", "https://example.com/twiml")]
    assert twilio.sms == [("+56911111111", "Alerta: Posible fraude detectado")]
    assert twilio.whatsapp == [("+56922222222", "Alerta: Posible fraude detectado")]
