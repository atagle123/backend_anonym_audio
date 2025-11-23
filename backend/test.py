from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import wave
from pathlib import Path
from typing import Iterable

import websockets
from dotenv import load_dotenv

DEFAULT_URI = "ws://localhost:8000/ws/audio-flag"
CHUNK_SAMPLES = 3200  # 0.2s of audio at 16kHz
PCM_SAMPLE_WIDTH = 2  # bytes (16-bit)
DEFAULT_TTS_TEXT = "The first move is what sets everything in motion."
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "pcm_16000"


def _chunk_bytes(payload: bytes, chunk_size: int) -> Iterable[bytes]:
    for start in range(0, len(payload), chunk_size):
        yield payload[start : start + chunk_size]


def _load_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getnchannels() != 1:
            raise ValueError("WAV file must be mono.")
        if wav_file.getsampwidth() != 2:
            raise ValueError("WAV file must be 16-bit PCM.")
        if wav_file.getframerate() != 16_000:
            raise ValueError("WAV file must be sampled at 16kHz.")
        return wav_file.readframes(wav_file.getnframes())


def _generate_tts_audio(
    text: str,
    voice_id: str,
    model_id: str,
    output_format: str,
) -> bytes:
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is required to generate ElevenLabs audio."
        )

    # Import lazily so the dependency is only needed when TTS is requested.
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=api_key)
    audio_stream = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )

    audio_bytes = b"".join(audio_stream)
    if output_format not in {"pcm_16000", "pcm_22050", "pcm_44100"}:
        raise ValueError(
            f"Output format '{output_format}' is not raw PCM. "
            "Use a PCM output (e.g. 'pcm_16000') so the websocket can relay 16-bit audio."
        )

    if output_format != "pcm_16000":
        raise ValueError(
            f"Output format '{output_format}' uses a different sample rate. "
            "Set '--output-format pcm_16000' to match the service expectations."
        )

    return audio_bytes


async def _send_audio(
    ws: websockets.WebSocketClientProtocol, audio_bytes: bytes, chunk_size: int
) -> None:
    for chunk in _chunk_bytes(audio_bytes, chunk_size):
        await ws.send(chunk)
        await asyncio.sleep(0)  # cooperative yield
    await ws.send(json.dumps({"event": "end"}))


async def _receive_messages(ws: websockets.WebSocketClientProtocol) -> None:
    async for message in ws:
        if isinstance(message, bytes):
            print(f"[binary] {len(message)} bytes")
            continue

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            print(f"[text] {message}")
            continue

        event = payload.get("event")
        print(f"[event] {event}: {payload}")
        if event == "summary":
            break


async def stream_audio(uri: str, audio_bytes: bytes, chunk_size: int) -> None:
    async with websockets.connect(uri, max_size=None) as ws:
        ready = await ws.recv()
        print(f"[event] ready: {ready}")
        receiver = asyncio.create_task(_receive_messages(ws))
        await _send_audio(ws, audio_bytes, chunk_size)
        await receiver


async def stream_file(uri: str, audio_path: Path) -> None:
    audio_bytes = await asyncio.to_thread(_load_wav, audio_path)
    chunk_size = CHUNK_SAMPLES * PCM_SAMPLE_WIDTH
    await stream_audio(uri, audio_bytes, chunk_size)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream a WAV file to the /ws/audio-flag websocket."
    )
    parser.add_argument(
        "audio",
        nargs="?",
        type=Path,
        help="Path to a WAV file (PCM16 mono @16kHz). Required unless --text is used.",
    )
    parser.add_argument(
        "--uri",
        default=DEFAULT_URI,
        help=f"Websocket URI for the audio flag service (default: {DEFAULT_URI}).",
    )
    parser.add_argument(
        "--text",
        nargs="?",
        const=DEFAULT_TTS_TEXT,
        help=(
            "Generate audio via ElevenLabs from this text instead of reading a WAV file. "
            "If used without a value, a default prompt is sent."
        ),
    )
    parser.add_argument(
        "--voice-id",
        default=DEFAULT_VOICE_ID,
        help=f"ElevenLabs voice ID to use with --text (default: {DEFAULT_VOICE_ID}).",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help=f"ElevenLabs model ID to use with --text (default: {DEFAULT_MODEL_ID}).",
    )
    parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        help=(
            "Audio format for ElevenLabs synthesis (default: "
            f"{DEFAULT_OUTPUT_FORMAT}). Must be a PCM format."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    if args.text is not None:
        audio_bytes = _generate_tts_audio(
            text=args.text,
            voice_id=args.voice_id,
            model_id=args.model_id,
            output_format=args.output_format,
        )
        chunk_size = CHUNK_SAMPLES * PCM_SAMPLE_WIDTH
        asyncio.run(stream_audio(args.uri, audio_bytes, chunk_size))
        return

    if args.audio is not None:
        asyncio.run(stream_file(args.uri, args.audio))
        return

    raise SystemExit("Provide a WAV file path or use --text to synthesize audio.")


if __name__ == "__main__":
    main()
