from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, AsyncIterable, Iterable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.audioAnonymizer.service import AudioAnonymizerService

LOGGER = logging.getLogger(__name__)


class AudioAnonymizeRequest(BaseModel):
    audio_b64: str = Field(..., description="Base64-encoded PCM16 audio payload.")


class AudioAnonymizeResponse(BaseModel):
    audio_b64: str = Field(..., description="Base64-encoded anonymized audio.")
    audio_format: str = Field(..., description="Format identifier for the synthesized audio.")


async def _ensure_bytes(payload: Any) -> bytes:
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")

    if hasattr(payload, "__aiter__"):
        data = bytearray()
        async for chunk in payload:  # type: ignore[attr-defined]
            if chunk is None:
                continue
            data.extend(await _ensure_bytes(chunk))
        return bytes(data)

    if isinstance(payload, Iterable):
        data = bytearray()
        for chunk in payload:
            if chunk is None:
                continue
            data.extend(await _ensure_bytes(chunk))
        return bytes(data)

    raise TypeError("Unsupported anonymizer payload; expected bytes-like data.")


def create_audio_anonymizer_router(
    anonymizer_service: AudioAnonymizerService,
) -> APIRouter:
    router = APIRouter()

    async def _single_chunk_stream(data: bytes) -> AsyncIterable[bytes]:
        yield data

    @router.post(
        "/anonymize-audio",
        response_model=AudioAnonymizeResponse,
        summary="Anonymize user audio by redacting sensitive terms.",
    )
    async def anonymize_audio(payload: AudioAnonymizeRequest) -> AudioAnonymizeResponse:
        try:
            audio_bytes = base64.b64decode(payload.audio_b64, validate=True)
        except binascii.Error as exc:
            raise HTTPException(status_code=400, detail="Invalid base64 audio payload.") from exc

        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio payload is empty.")

        try:
            anonymized = await anonymizer_service.anonymize_stream(
                _single_chunk_stream(audio_bytes)
            )
        except Exception as exc:  # pragma: no cover - logged then re-raised
            LOGGER.exception("Audio anonymization failed.")
            raise HTTPException(status_code=500, detail="Failed to anonymize audio.") from exc

        try:
            anonymized_bytes = await _ensure_bytes(anonymized)
        except TypeError as exc:
            LOGGER.exception("Unsupported anonymizer payload.")
            raise HTTPException(
                status_code=500,
                detail="Anonymizer returned an unsupported payload format.",
            ) from exc

        encoded = base64.b64encode(anonymized_bytes).decode("ascii")
        output_format = getattr(
            anonymizer_service, "_synthesis_output_format", "mp3_44100_128"
        )
        return AudioAnonymizeResponse(
            audio_b64=encoded,
            audio_format=output_format,
        )

    return router
