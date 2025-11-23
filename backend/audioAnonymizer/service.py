import asyncio
import base64
import os
import re
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from elevenlabs import (
    AudioFormat,
    CommitStrategy,
    ElevenLabs,
    RealtimeAudioOptions,
    VoiceSettings,
)
from elevenlabs.play import play
from elevenlabs.realtime.connection import RealtimeEvents

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY is not set.")

VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam voice
MODEL_ID = "eleven_multilingual_v2"
PCM_SAMPLE_RATE = 16000

client = ElevenLabs(api_key=API_KEY)


def filter_sensitive_words(text: str) -> str:
    """Replace sensitive words in text."""
    # Example: replace "clave" with "zzzz"
    return re.sub(r"\bclave\b", "zzzz", text, flags=re.IGNORECASE)


def pcm_stream_for_text(text: str):
    """Generate PCM chunks from text using TTS."""
    response = client.text_to_speech.stream(
        voice_id=VOICE_ID,
        text=text,
        model_id=MODEL_ID,
        output_format="pcm_16000",
        voice_settings=VoiceSettings(
            stability=0.0,
            similarity_boost=1.0,
            style=0.0,
            use_speaker_boost=True,
            speed=1.0,
        ),
    )
    for chunk in response:
        if chunk:
            yield chunk


async def transcribe_and_filter(text: str) -> str:
    """Send audio to Scribe v2 realtime, filter unsafe words, return anonymized transcript."""
    connection = await client.speech_to_text.realtime.connect(
        RealtimeAudioOptions(
            model_id="scribe_v2_realtime",
            language_code="es",
            audio_format=AudioFormat.PCM_16000,
            sample_rate=PCM_SAMPLE_RATE,
            commit_strategy=CommitStrategy.MANUAL,
            include_timestamps=False,
        )
    )

    transcripts: List[str] = []
    transcript_ready = asyncio.Event()

    def handle_committed(data: Dict):
        transcript = data.get("transcript") or data.get("text")
        if transcript:
            filtered = filter_sensitive_words(transcript)
            transcripts.append(filtered)
        transcript_ready.set()

    def handle_error(data: Dict):
        print(f"Realtime transcription error: {data}")
        transcript_ready.set()

    connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, handle_committed)
    connection.on(RealtimeEvents.ERROR, handle_error)

    try:
        for chunk in pcm_stream_for_text(text):
            payload = base64.b64encode(chunk).decode("ascii")
            await connection.send({"audio_base_64": payload})

        await connection.commit()
        await asyncio.wait_for(transcript_ready.wait(), timeout=15)
    finally:
        await connection.close()

    return " ".join(transcripts).strip()


def synthesize_audio(text: str) -> bytes:
    """Generate anonymized audio from text."""
    return client.text_to_speech.convert(
        text=text,
        voice_id=VOICE_ID,
        model_id="eleven_flash_v2_5",
        output_format="mp3_44100_128",
    )


async def auto_anonymizer_service(seed_text: str):
    """Main service: transcribe, filter, synthesize audio."""
    print(f"Input text/audio: {seed_text}")

    anonymized_transcript = await transcribe_and_filter(seed_text)
    if not anonymized_transcript:
        raise RuntimeError("No transcript received.")

    print(f"Anonymized transcript: {anonymized_transcript}")

    audio = synthesize_audio(anonymized_transcript)
    play(audio)  # Play locally


if __name__ == "__main__":
    asyncio.run(auto_anonymizer_service("Te comparto mi clave."))
