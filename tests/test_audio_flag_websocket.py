from __future__ import annotations

import json
from typing import AsyncIterable, AsyncIterator, Iterable, List

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.FilterService.filter import FilterService
from backend.api.audio_flag_websocket import create_audio_flag_router
from backend.services.audio_flag_service import AudioFlagService, FlaggedTranscript
from backend.services.speech_to_text import SpeechToTextService, TranscriptSegment


def _chunk_bytes(payload: bytes, chunk_size: int) -> Iterable[bytes]:
    for start in range(0, len(payload), chunk_size):
        yield payload[start : start + chunk_size]


class FakeSpeechToTextService(SpeechToTextService):
    def __init__(self, segments: List[TranscriptSegment]) -> None:
        self._segments = segments
        self.received = bytearray()

    async def stream_transcribe(
        self, audio_chunks: AsyncIterable[bytes]
    ) -> AsyncIterator[TranscriptSegment]:
        async for chunk in audio_chunks:
            self.received.extend(chunk)
        for segment in self._segments:
            yield segment


class StubNotifier:
    def __init__(self) -> None:
        self.flagged: List[FlaggedTranscript] = []

    async def notify_flagged(self, transcript: FlaggedTranscript) -> None:
        self.flagged.append(transcript)


def test_audio_flag_endpoint_streams_audio_bytes() -> None:
    segments = [
        TranscriptSegment(text="Hola mundo", is_final=False),
        TranscriptSegment(text="La clave secreta es 1234", is_final=True),
    ]
    speech_to_text = FakeSpeechToTextService(segments)
    filter_service_user = FilterService([r"\bclave\b"])
    filter_service_scammer = FilterService([r"\bclave\b"])
    audio_service = AudioFlagService(
        speech_to_text,
        filter_service_user=filter_service_user,
        filter_service_scammer=filter_service_scammer,
    )
    notifier = StubNotifier()

    app = FastAPI()
    app.include_router(create_audio_flag_router(audio_service, notifier))

    payload = (b"\x01\x02" * 1600) + (b"\x03\x04" * 1600)
    chunk_size = 320

    with TestClient(app) as client:
        with client.websocket_connect("/ws/audio-flag") as websocket:
            ready = websocket.receive_json()
            assert ready == {"event": "ready"}

            for chunk in _chunk_bytes(payload, chunk_size):
                websocket.send_bytes(chunk)
            websocket.send_text(json.dumps({"event": "end"}))

            events: List[dict] = []
            while True:
                response = websocket.receive_json()
                events.append(response)
                if response.get("event") == "summary":
                    break

    assert speech_to_text.received == payload

    transcripts = [event for event in events if event["event"] == "transcript"]
    assert len(transcripts) == len(segments)
    assert transcripts[0]["text"] == segments[0].text
    assert transcripts[0]["flagged"] is False
    assert transcripts[1]["text"] == segments[1].text
    assert transcripts[1]["flagged"] is True

    summary = events[-1]
    assert summary["event"] == "summary"
    assert summary["flagged"] is True

    assert len(notifier.flagged) == 1
    assert notifier.flagged[0].text == segments[1].text
