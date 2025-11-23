from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterable, List, Optional

from dotenv import load_dotenv
from elevenlabs import ElevenLabs

from backend.FilterService.filter import FilterService
from backend.FilterService.userFilter import UserFilter
from backend.services.speech_to_text import (
    ElevenLabsSpeechToTextService,
    SpeechToTextService,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY is not set.")

VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam voice
PCM_SAMPLE_RATE = 16_000
TRANSCRIPTION_MODEL_ID = "scribe_v2_realtime"
SYNTHESIS_MODEL_ID = "eleven_flash_v2_5"
SYNTHESIS_OUTPUT_FORMAT = "mp3_44100_128"

_elevenlabs_client = ElevenLabs(api_key=API_KEY)


class AudioAnonymizerService:
    """
    Listen to streamed audio, anonymize sensitive words, and synthesize sanitized speech.
    """

    def __init__(
        self,
        speech_to_text: SpeechToTextService,
        filter_service: FilterService,
        elevenlabs_client: ElevenLabs,
        voice_id: str = VOICE_ID,
        synthesis_model_id: str = SYNTHESIS_MODEL_ID,
        synthesis_output_format: str = SYNTHESIS_OUTPUT_FORMAT,
    ) -> None:
        self._speech_to_text = speech_to_text
        self._filter = filter_service
        self._client = elevenlabs_client
        self._voice_id = voice_id
        self._synthesis_model_id = synthesis_model_id
        self._synthesis_output_format = synthesis_output_format

    async def anonymize_stream(self, audio_chunks: AsyncIterable[bytes]) -> bytes:
        """
        Consume PCM16 mono audio chunks, return synthesized audio with sensitive
        information replaced by `zzzz`.
        """
        sanitized_segments: List[str] = []
        latest_partial: Optional[str] = None

        async for segment in self._speech_to_text.stream_transcribe(audio_chunks):
            if not segment.text:
                continue

            sanitized = self._filter.apply(segment.text, replacement="zzzz")
            if segment.is_final:
                sanitized_segments.append(sanitized)
                latest_partial = None
            else:
                latest_partial = sanitized

        if not sanitized_segments and latest_partial:
            sanitized_segments.append(latest_partial)

        anonymized_transcript = " ".join(sanitized_segments).strip()
        if not anonymized_transcript:
            raise RuntimeError("No transcript received from speech-to-text service.")

        return self._synthesize_audio(anonymized_transcript)

    def _synthesize_audio(self, text: str) -> bytes:
        return self._client.text_to_speech.convert(
            text=text,
            voice_id=self._voice_id,
            model_id=self._synthesis_model_id,
            output_format=self._synthesis_output_format,
        )


def build_audio_anonymizer_service(
    *,
    filter_service: Optional[FilterService] = None,
    speech_to_text: Optional[SpeechToTextService] = None,
) -> AudioAnonymizerService:
    """
    Factory helper that wires the default ElevenLabs streaming configuration together.
    """
    stt_service = speech_to_text or ElevenLabsSpeechToTextService(
        api_key=API_KEY,
        model_id=TRANSCRIPTION_MODEL_ID,
        language="es",
        sample_rate=PCM_SAMPLE_RATE,
        format_="pcm16",
    )
    active_filter = filter_service or UserFilter()
    return AudioAnonymizerService(
        speech_to_text=stt_service,
        filter_service=active_filter,
        elevenlabs_client=_elevenlabs_client,
    )
