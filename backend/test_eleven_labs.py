from __future__ import annotations

import argparse
import os
import sys
import tempfile
import wave
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

DEFAULT_TEXT = "Hola, esta es una prueba del generador de voz de ElevenLabs."
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam (es/en friendly)
DEFAULT_MODEL_ID = "eleven_flash_v2_5"
OUTPUT_FORMAT = "pcm_16000"
SAMPLE_RATE = 44_100
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes (16-bit)


def _resolve_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing ELEVENLABS_API_KEY. Export it or add it to your .env file."
        )
    return api_key


def _play_audio(audio_bytes: bytes) -> None:
    """
    Try to play raw PCM audio. Falls back to writing a WAV file when simpleaudio is absent.
    """
    try:
        import simpleaudio  # type: ignore
    except ImportError:
        output_path = Path(tempfile.gettempdir()) / "elevenlabs_test_output.wav"
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_bytes)
        print(
            "simpleaudio is not installed; wrote the clip to "
            f"{output_path} (16-bit PCM WAV)."
        )
        return

    play_obj = simpleaudio.play_buffer(
        audio_bytes,
        num_channels=CHANNELS,
        bytes_per_sample=SAMPLE_WIDTH,
        sample_rate=SAMPLE_RATE,
    )
    play_obj.wait_done()


def generate_audio(text: str, voice_id: str, model_id: str) -> bytes:
    client = ElevenLabs(api_key=_resolve_api_key())
    print("Requesting audio from ElevenLabs…")
    audio_stream = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=OUTPUT_FORMAT,
    )
    audio_bytes = b"".join(audio_stream)
    if not audio_bytes:
        raise SystemExit("ElevenLabs returned an empty audio payload.")
    print(f"Received {len(audio_bytes)} bytes (format={OUTPUT_FORMAT}).")
    return audio_bytes


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quick manual test that hits ElevenLabs TTS and plays the audio."
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="Text to synthesize (default: example Spanish sentence).",
    )
    parser.add_argument(
        "--voice-id",
        default=DEFAULT_VOICE_ID,
        help=f"ElevenLabs voice ID (default: {DEFAULT_VOICE_ID}).",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help=f"ElevenLabs model ID (default: {DEFAULT_MODEL_ID}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    audio_bytes = generate_audio(args.text, args.voice_id, args.model_id)
    _play_audio(audio_bytes)


if __name__ == "__main__":
    main()
