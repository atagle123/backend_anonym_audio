from __future__ import annotations

import asyncio
import inspect
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import AsyncIterable, AsyncIterator, Optional, Protocol

import websockets
from websockets.client import WebSocketClientProtocol

LOGGER = logging.getLogger(__name__)

_CONNECT_HEADER_KWARG: Optional[str] = None
try:
    _connect_params = inspect.signature(websockets.connect).parameters
    for candidate in ("additional_headers", "extra_headers"):
        if candidate in _connect_params:
            _CONNECT_HEADER_KWARG = candidate
            break
except (ValueError, TypeError):
    # If introspection fails we fall back to the legacy kwarg. A failure will
    # surface later when we try to connect, which is fine.
    _CONNECT_HEADER_KWARG = "extra_headers"


@dataclass
class TranscriptSegment:
    """Text emitted by the speech-to-text engine."""

    text: str
    is_final: bool = False


class SpeechToTextService(Protocol):
    """Streaming speech-to-text API."""

    async def stream_transcribe(
        self, audio_chunks: AsyncIterable[bytes]
    ) -> AsyncIterator[TranscriptSegment]:
        """Yield transcript segments as they become available."""


class ElevenLabsSpeechToTextService:
    """
    ElevenLabs real-time Scribe v2 wrapper.

    The service keeps the contract extremely small: feed it PCM16 mono chunks
    (16kHz by default) and iterate over the yielded text segments. Internally it
    brokers a WebSocket connection against the ElevenLabs streaming endpoint.
    """

    _STREAM_URL = "wss://api.elevenlabs.io/v1/speech-to-text/stream"

    def __init__(
        self,
        api_key: str,
        model_id: str = "scribe_v2",
        language: str = "es",
        sample_rate: int = 16_000,
        format_: str = "pcm16",
        connection_timeout: int = 10,
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key is required")

        self._api_key = api_key
        self._model_id = model_id
        self._language = language
        self._sample_rate = sample_rate
        self._format = format_
        self._connection_timeout = connection_timeout

    async def stream_transcribe(
        self, audio_chunks: AsyncIterable[bytes]
    ) -> AsyncIterator[TranscriptSegment]:
        """
        Forward binary audio frames to ElevenLabs and re-yield their transcript payloads.

        The ElevenLabs real-time API currently speaks WebSocket with an initial JSON
        configuration message followed by raw audio frames. Responses are emitted as
        JSON text frames containing partial or final transcripts. The payload shape
        is documented in their API reference; we only care about `text` and
        optional `is_final` flags here.
        """
        sender_task: Optional[asyncio.Task[None]] = None
        try:
            headers = {
                "xi-api-key": self._api_key,
                "accept": "application/json",
            }
            connect_kwargs = {
                "open_timeout": self._connection_timeout,
                "max_size": None,
            }
            if not _CONNECT_HEADER_KWARG:
                raise RuntimeError("Unsupported websockets version: missing header kwarg")
            connect_kwargs[_CONNECT_HEADER_KWARG] = headers

            async with websockets.connect(
                self._STREAM_URL,
                **connect_kwargs,
            ) as ws:
                await self._send_config(ws)
                sender_task = asyncio.create_task(
                    self._forward_audio(ws, audio_chunks), name="elevenlabs-audio-forward"
                )

                async for text_frame in ws:
                    # ElevenLabs currently sends transcripts in text frames.
                    if isinstance(text_frame, (bytes, bytearray)):
                        LOGGER.debug(
                            "Ignoring unexpected binary frame from ElevenLabs (%s bytes)",
                            len(text_frame),
                        )
                        continue

                    payload = self._decode_payload(text_frame)
                    if payload is None:
                        continue

                    event_type = payload.get("type")
                    if event_type == "transcript":
                        data = payload.get("data", {})
                        text = data.get("text")
                        if text:
                            yield TranscriptSegment(
                                text=text, is_final=data.get("is_final", False)
                            )
                    elif event_type == "error":
                        raise RuntimeError(payload.get("message", "ElevenLabs error"))
                    elif event_type == "session_information":
                        LOGGER.debug("Session info: %s", payload)
                    else:
                        LOGGER.debug("Unhandled ElevenLabs frame: %s", payload)
        except Exception:
            LOGGER.exception("Real-time transcription failed")
            raise
        finally:
            # Ensure the sender task is fully cleaned up.
            if sender_task:
                sender_task.cancel()
                with suppress(asyncio.CancelledError):
                    await sender_task

    async def _send_config(self, ws: WebSocketClientProtocol) -> None:
        config_payload = {
            "type": "session.update",
            "data": {
                "model": self._model_id,
                "language": self._language,
                "audio_format": self._format,
                "sample_rate_hz": self._sample_rate,
            },
        }
        await ws.send(json.dumps(config_payload))

    async def _forward_audio(
        self, ws: WebSocketClientProtocol, audio_chunks: AsyncIterable[bytes]
    ) -> None:
        async for chunk in audio_chunks:
            if not chunk:
                continue
            await ws.send(chunk)

        # Signal the end of the audio stream. ElevenLabs expects an explicit event.
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await ws.send(json.dumps({"type": "response.create"}))

    @staticmethod
    def _decode_payload(raw_frame: str) -> Optional[dict]:
        try:
            return json.loads(raw_frame)
        except json.JSONDecodeError:
            LOGGER.debug("Failed to decode ElevenLabs frame: %s", raw_frame[:200])
        return None
