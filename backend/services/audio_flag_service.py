from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterable, AsyncIterator

from backend.FilterService.filter import FilterService

from .speech_to_text import SpeechToTextService, TranscriptSegment


@dataclass
class FlaggedTranscript:
    """Combination of transcript content and the filter evaluation."""

    text: str
    flagged: bool
    is_final: bool


class AudioFlagService:
    """
    Coordinates streaming transcription and post-processing filters.

    The service keeps no transport concerns (those live in the API layer). It
    simply consumes an async iterable of audio frames and re-yields text +
    flagging information as soon as the STT provider emits them.
    """

    def __init__(
        self, speech_to_text: SpeechToTextService, filter_service: FilterService
    ) -> None:
        self._speech_to_text = speech_to_text
        self._filter = filter_service

    async def process_stream(
        self, audio_chunks: AsyncIterable[bytes]
    ) -> AsyncIterator[FlaggedTranscript]:
        async for segment in self._speech_to_text.stream_transcribe(audio_chunks):
            yield self._flag_segment(segment)

    def _flag_segment(self, segment: TranscriptSegment) -> FlaggedTranscript:
        flagged = self._filter.filter(segment.text)
        return FlaggedTranscript(
            text=segment.text, flagged=flagged, is_final=segment.is_final
        )
