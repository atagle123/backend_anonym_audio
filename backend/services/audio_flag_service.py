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
        self,
        speech_to_text: SpeechToTextService,
        filter_service_user: FilterService,
        filter_service_scammer: FilterService,
    ) -> None:
        self._speech_to_text = speech_to_text
        self._filter_user = filter_service_user
        self._filter_scammer = filter_service_scammer

    async def process_stream(
        self, audio_chunks: AsyncIterable[bytes], role: str
    ) -> AsyncIterator[FlaggedTranscript]:
        """
        Stream audio chunks, transcribe, and flag each transcript according to the role.
        """

        async for segment in self._speech_to_text.stream_transcribe(audio_chunks):
            yield self._flag_segment(segment, role)

    def _flag_segment(self, segment: TranscriptSegment, role: str) -> FlaggedTranscript:
        """
        Apply the appropriate filter based on role.
        """

        role_key = (role or "").lower()
        if role_key == "user":
            filter_service = self._filter_user
        else:
            # Default to scammer filter when role is unknown to err on the safe side.
            filter_service = self._filter_scammer

        flagged = filter_service.filter(segment.text)
        return FlaggedTranscript(
            text=segment.text, flagged=flagged, is_final=segment.is_final
        )
