from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.services import AudioFlagService, FlaggedTranscript, NotificationService

LOGGER = logging.getLogger(__name__)


def create_audio_flag_router(
    service: AudioFlagService, notifier: Optional[NotificationService] = None
) -> APIRouter:
    """
    Register streaming audio flagging routes.

    The router exposes a single WebSocket endpoint:

    Path: `/ws/audio-flag`
    Messages:
        - Binary frames: raw PCM16 mono chunks at 16kHz.
        - Text frames:
            * `{"event": "end"}` to close the upstream stream gracefully.
    Responses:
        - `{"event": "transcript", "text": "...", "flagged": true, "is_final": false}`
        - `{"event": "summary", "flagged": true}` once the stream completes.
        - `{"event": "error", "message": "..."}` if the upstream provider fails.
    """

    router = APIRouter()

    @router.websocket("/ws/audio-flag")
    async def audio_flag_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_json({"event": "ready"})

        audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        any_flagged = False
        notification_sent = False
        first_flagged_segment: Optional[FlaggedTranscript] = None

        async def audio_chunk_stream() -> AsyncIterator[bytes]:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                yield chunk

        async def receiver() -> None:
            try:
                while True:
                    message = await ws.receive()
                    if message.get("bytes") is not None:
                        await audio_queue.put(message["bytes"])
                        continue

                    text_message = message.get("text")
                    if text_message is None:
                        continue

                    try:
                        payload = json.loads(text_message)
                    except json.JSONDecodeError:
                        # Non-JSON text frames are ignored for now.
                        continue

                    if payload.get("event") == "end":
                        break
            except WebSocketDisconnect:
                pass
            finally:
                await audio_queue.put(None)

        async def dispatch_notification(segment: FlaggedTranscript) -> None:
            nonlocal notification_sent
            if notifier is None or notification_sent:
                return
            try:
                await notifier.notify_flagged(segment)
                notification_sent = True
            except Exception:  # pragma: no cover - best-effort alerts
                LOGGER.exception("Failed to dispatch Twilio alert")
                notification_sent = False

        async def sender() -> None:
            nonlocal any_flagged, first_flagged_segment
            try:
                async for flagged in service.process_stream(audio_chunk_stream()):
                    any_flagged = any_flagged or flagged.flagged
                    if flagged.flagged:
                        if first_flagged_segment is None:
                            first_flagged_segment = flagged
                        await dispatch_notification(flagged)
                    await ws.send_json(
                        {
                            "event": "transcript",
                            "text": flagged.text,
                            "flagged": flagged.flagged,
                            "is_final": flagged.is_final,
                        }
                    )
            except WebSocketDisconnect:
                pass
            except Exception as exc:  # pragma: no cover - defensive
                await ws.send_json(
                    {"event": "error", "message": f"Transcription failed: {exc}"}
                )
                raise

        await asyncio.gather(receiver(), sender())

        # Once the gather returns we can emit a summary flag.
        if (
            any_flagged
            and first_flagged_segment is not None
            and notifier is not None
            and not notification_sent
        ):
            await dispatch_notification(first_flagged_segment)

        if ws.application_state != WebSocketState.DISCONNECTED:
            await ws.send_json({"event": "summary", "flagged": any_flagged})
            await ws.close()

    return router
