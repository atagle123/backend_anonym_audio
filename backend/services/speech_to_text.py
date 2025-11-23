from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import AsyncIterable, AsyncIterator, Optional, Protocol
from urllib.parse import urlencode

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

    _STREAM_BASE_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    def __init__(
        self,
        api_key: str,
        model_id: str = "scribe_v2_realtime",
        language: str = "es",
        sample_rate: int = 16_000,
        format_: str = "pcm16",
        connection_timeout: int = 10,
        commit_strategy: str = "vad",
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key is required")

        self._api_key = api_key
        self._model_id = model_id
        self._language = language
        self._sample_rate = sample_rate
        self._encoding = self._normalise_encoding(format_, sample_rate)
        self._connection_timeout = connection_timeout
        self._commit_strategy = self._normalise_commit_strategy(commit_strategy)

    async def stream_transcribe(
        self, audio_chunks: AsyncIterable[bytes]
    ) -> AsyncIterator[TranscriptSegment]:
        """
        Forward audio frames to ElevenLabs and re-yield their transcript payloads.

        The realtime endpoint expects JSON control frames with base64-encoded audio
        chunks. Responses arrive as JSON text frames containing partial or committed
        transcripts.
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

            stream_url = self._build_stream_url()

            async with websockets.connect(
                stream_url,
                **connect_kwargs,
            ) as ws:
                sender_task = asyncio.create_task(
                    self._forward_audio(ws, audio_chunks), name="elevenlabs-audio-forward"
                )

                async for frame in ws:
                    payload = self._decode_payload(frame)
                    if payload is None:
                        continue

                    message_type = payload.get("message_type")
                    if message_type == "partial_transcript":
                        text = self._extract_transcript(payload)
                        if text:
                            yield TranscriptSegment(text=text, is_final=False)
                    elif message_type in {
                        "committed_transcript",
                        "committed_transcript_with_timestamps",
                    }:
                        text = self._extract_transcript(payload)
                        if text:
                            yield TranscriptSegment(text=text, is_final=True)
                    elif message_type in {"auth_error", "quota_exceeded"}:
                        detail = payload.get("error") or payload.get("message")
                        raise PermissionError(detail or message_type)
                    elif message_type == "error":
                        detail = payload.get("error") or payload.get("message")
                        raise RuntimeError(detail or "ElevenLabs realtime error")
                    elif message_type == "session_started":
                        LOGGER.debug("ElevenLabs realtime session started")
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

    def _build_stream_url(self) -> str:
        params = {
            "model_id": self._model_id,
            "encoding": self._encoding,
            "sample_rate": str(self._sample_rate),
            "commit_strategy": self._commit_strategy,
        }
        if self._language:
            params["language_code"] = self._language
        query = urlencode(params)
        return f"{self._STREAM_BASE_URL}?{query}"

    @staticmethod
    def _normalise_encoding(format_: str, sample_rate: int) -> str:
        normalized = (format_ or "").lower()
        if normalized.startswith("pcm_"):
            return normalized
        if normalized in {"pcm16", "pcm"}:
            return f"pcm_{sample_rate}"
        raise ValueError(f"Unsupported audio encoding for ElevenLabs realtime: {format_}")

    @staticmethod
    def _normalise_commit_strategy(strategy: str) -> str:
        value = (strategy or "vad").lower()
        if value not in {"vad", "manual"}:
            raise ValueError(f"Unsupported commit strategy for ElevenLabs realtime: {strategy}")
        return value

    async def _forward_audio(
        self, ws: WebSocketClientProtocol, audio_chunks: AsyncIterable[bytes]
    ) -> None:
        async for chunk in audio_chunks:
            if not chunk:
                continue
            await ws.send(
                json.dumps(
                    {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                        "commit": False,
                        "sample_rate": self._sample_rate,
                    }
                )
            )

        # Flush any buffered audio before closing down.
        await ws.send(
            json.dumps(
                {
                    "message_type": "input_audio_chunk",
                    "audio_base_64": "",
                    "commit": True,
                    "sample_rate": self._sample_rate,
                }
            )
        )

    @staticmethod
    def _decode_payload(raw_frame: str | bytes | bytearray) -> Optional[dict]:
        if isinstance(raw_frame, (bytes, bytearray)):
            try:
                raw_frame = raw_frame.decode("utf-8")
            except UnicodeDecodeError:
                LOGGER.debug("Failed to decode ElevenLabs binary frame (%s bytes)", len(raw_frame))
                return None
        try:
            return json.loads(raw_frame)
        except json.JSONDecodeError:
            LOGGER.debug("Failed to decode ElevenLabs frame: %s", raw_frame[:200])
        return None

    @staticmethod
    def _extract_transcript(payload: dict) -> Optional[str]:
        """
        ElevenLabs sends transcript text in slightly different shapes depending on the
        event. Fallback through the common field names.
        """
        for key in ("transcript", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("transcript", "text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None
