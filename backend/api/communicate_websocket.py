from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.services import AudioFlagService, FlaggedTranscript

if TYPE_CHECKING:
    pass

LOGGER = logging.getLogger(__name__)

DEFAULT_SILENCE_MP3 = base64.b64decode(
    (
        "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//uQxAADwAABpAAA"
        "ACAAADSAAAAETEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVV//uSxDkDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7ksQ5A8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVV//uSxDkDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7ksQ5A8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVV//uSxDkDwAABpAAAACAAADSAAAAEVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/7ksQ5A8AAAaQAAAAgAAA0gAAABFVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
        "VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU="
    )
)


async def _collect_audio_bytes(payload: object) -> bytes:
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode("utf-8")

    if hasattr(payload, "__aiter__"):
        data = bytearray()
        async for chunk in payload:  # type: ignore[attr-defined]
            if isinstance(chunk, (bytes, bytearray, memoryview)):
                data.extend(chunk)
            elif chunk is None:
                continue
            else:
                data.extend(bytes(chunk))
        return bytes(data)

    if isinstance(payload, Iterable):
        data = bytearray()
        for chunk in payload:
            if isinstance(chunk, (bytes, bytearray, memoryview)):
                data.extend(chunk)
            elif chunk is None:
                continue
            else:
                data.extend(bytes(chunk))
        return bytes(data)

    raise TypeError("Expected bytes-like payload for anonymized audio")


@dataclass
class Client:
    client_id: str
    role: str
    websocket: WebSocket


class Room:
    """Manage the set of active websocket connections for a room."""

    def __init__(self) -> None:
        self._clients: Dict[int, Client] = {}
        self._lock = asyncio.Lock()

    def _prune_disconnected_locked(self) -> None:
        stale_keys = [
            key
            for key, client in list(self._clients.items())
            if not _is_websocket_connected(client.websocket)
        ]
        for key in stale_keys:
            stale = self._clients.pop(key, None)
            if stale:
                LOGGER.debug("Pruned disconnected websocket %s", stale.client_id)

    async def join(self, ws: WebSocket, role: str) -> Client:
        client = Client(client_id=uuid.uuid4().hex, role=role, websocket=ws)
        async with self._lock:
            self._prune_disconnected_locked()
            self._clients[id(ws)] = client
        return client

    async def leave(self, ws: WebSocket) -> Optional[Client]:
        async with self._lock:
            return self._clients.pop(id(ws), None)

    async def peers(self, ws: WebSocket) -> List[Client]:
        async with self._lock:
            self._prune_disconnected_locked()
            return [
                client
                for key, client in self._clients.items()
                if key != id(ws) and _is_websocket_connected(client.websocket)
            ]

    async def clients(self) -> List[Client]:
        async with self._lock:
            self._prune_disconnected_locked()
            return list(self._clients.values())

    async def is_empty(self) -> bool:
        async with self._lock:
            self._prune_disconnected_locked()
            return not self._clients


_rooms: Dict[str, Room] = {}
_rooms_lock = asyncio.Lock()

_filtered_rooms: Dict[str, Room] = {}
_filtered_rooms_lock = asyncio.Lock()


async def _get_room(room_id: str) -> Room:
    async with _rooms_lock:
        room = _rooms.get(room_id)
        if room is None:
            room = Room()
            _rooms[room_id] = room
        return room


async def _cleanup_room(room_id: str, room: Room) -> None:
    if not await room.is_empty():
        return
    async with _rooms_lock:
        if await room.is_empty():
            _rooms.pop(room_id, None)


async def _get_filtered_room(room_id: str) -> Room:
    async with _filtered_rooms_lock:
        room = _filtered_rooms.get(room_id)
        if room is None:
            room = Room()
            _filtered_rooms[room_id] = room
        return room


async def _cleanup_filtered_room(room_id: str, room: Room) -> None:
    if not await room.is_empty():
        return
    async with _filtered_rooms_lock:
        if await room.is_empty():
            _filtered_rooms.pop(room_id, None)


def _is_websocket_connected(ws: WebSocket) -> bool:
    return (
        getattr(ws, "application_state", WebSocketState.DISCONNECTED)
        == WebSocketState.CONNECTED
        and getattr(ws, "client_state", WebSocketState.DISCONNECTED)
        == WebSocketState.CONNECTED
    )


async def _safe_disconnect_peer(room: Room, peer: Client, *, notify: bool) -> None:
    departed = await room.leave(peer.websocket)
    if departed and notify:
        message = {
            "event": "peer_left",
            "client_id": departed.client_id,
            "role": departed.role,
        }
        with suppress(Exception):
            await _notify_peers(room, message, exclude=peer.websocket)

    with suppress(Exception):
        await peer.websocket.close()


async def _handle_broadcast_failures(
    room: Room,
    peers: List[Client],
    results: List[object],
    log_template: str,
    *,
    notify_on_disconnect: bool,
) -> None:
    for peer, result in zip(peers, results):
        if isinstance(result, Exception):
            LOGGER.warning(log_template, peer.client_id, result)
            await _safe_disconnect_peer(room, peer, notify=notify_on_disconnect)


async def _broadcast_text(room: Room, sender: WebSocket, payload: str) -> None:
    peers = await room.peers(sender)
    if not peers:
        return
    tasks = [peer.websocket.send_text(payload) for peer in peers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await _handle_broadcast_failures(
        room,
        peers,
        results,
        "Broadcast to peer %s failed: %s",
        notify_on_disconnect=True,
    )


async def _notify_peers(
    room: Room, payload: dict, exclude: Optional[WebSocket] = None
) -> None:
    clients = await room.clients()
    if not clients:
        return
    tasks = []
    recipients: List[Client] = []
    for client in clients:
        if exclude is not None and client.websocket is exclude:
            continue
        recipients.append(client)
        tasks.append(client.websocket.send_json(payload))

    if not tasks:
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    await _handle_broadcast_failures(
        room,
        recipients,
        results,
        "Notification to peer %s failed: %s",
        notify_on_disconnect=False,
    )


async def _broadcast_flagged_audio(
    room: Room,
    sender: Client,
    audio_payload: bytes,
    flagged: FlaggedTranscript,
) -> None:
    if not audio_payload:
        return

    peers = await room.peers(sender.websocket)
    if not peers:
        return

    payload = bytes(len(audio_payload)) if flagged.flagged else audio_payload
    audio_b64 = base64.b64encode(payload).decode("ascii")
    message = {
        "event": "audio",
        "client_id": sender.client_id,
        "role": sender.role,
        "flagged": flagged.flagged,
        "is_final": flagged.is_final,
        "transcript": flagged.text,
        "audio_b64": audio_b64,
    }

    tasks = [peer.websocket.send_json(message) for peer in peers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await _handle_broadcast_failures(
        room,
        peers,
        results,
        "Flagged audio broadcast to %s failed: %s",
        notify_on_disconnect=True,
    )


async def _broadcast_raw_audio(
    room: Room, sender: Client, audio_payload: bytes
) -> None:
    if not audio_payload:
        return

    peers = await room.peers(sender.websocket)
    if not peers:
        return

    audio_b64 = base64.b64encode(audio_payload).decode("ascii")
    message = {
        "event": "audio_raw",
        "client_id": sender.client_id,
        "role": sender.role,
        "audio_b64": audio_b64,
    }

    tasks = [peer.websocket.send_json(message) for peer in peers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await _handle_broadcast_failures(
        room,
        peers,
        results,
        "Raw audio broadcast to %s failed: %s",
        notify_on_disconnect=True,
    )


async def _broadcast_anonymized_audio(
    room: Room,
    sender: Client,
    audio_payload: bytes,
    *,
    transcript: str,
    flagged: bool,
    audio_format: str = "mp3",
    event: str = "audio_anonymized",
    target_role: str = "scammer",
) -> None:
    if not audio_payload:
        return

    peers = await room.peers(sender.websocket)
    targets = [peer for peer in peers if peer.role == target_role]
    if not targets:
        return

    payload = DEFAULT_SILENCE_MP3 if flagged else audio_payload
    audio_b64 = base64.b64encode(payload).decode("ascii")
    message = {
        "event": event,
        "client_id": sender.client_id,
        "role": sender.role,
        "flagged": flagged,
        "is_final": True,
        "transcript": transcript,
        "audio_b64": audio_b64,
        "audio_format": audio_format,
    }

    tasks = [peer.websocket.send_json(message) for peer in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await _handle_broadcast_failures(
        room,
        targets,
        results,
        "Anonymized audio broadcast to %s failed: %s",
        notify_on_disconnect=True,
    )


def _aggregate_flagged_results(results: List[FlaggedTranscript]) -> tuple[str, bool]:
    transcript_parts = [item.text for item in results if item.text]
    transcript = " ".join(transcript_parts).strip()
    if not transcript:
        final_with_text = next((item for item in reversed(results) if item.text), None)
        transcript = final_with_text.text if final_with_text else ""
    flagged = any(item.flagged for item in results)
    return transcript, flagged


def create_communicate_router(audio_service: AudioFlagService) -> APIRouter:
    """
    Register a websocket endpoint that relays binary audio frames between peers
    after passing them through the AudioFlagService.

    Path: `/ws/communicate/{room_id}`
    Notes:
        - Peers join a logical room identified by `room_id`.
        - Clients must declare their role via `?role=user|scammer`.
        - Incoming audio is transcribed using the provided AudioFlagService.
          Once the transcript is flagged, the audio chunk plus metadata is sent
          to the other peers.
        - Text frames are forwarded as-is for out-of-band coordination.
        - Raw audio chunks are broadcast immediately for low-latency playback.
        - Lifecycle events are emitted to all peers (`peer_joined`, `peer_left`).
    """

    router = APIRouter()

    @router.websocket("/ws/communicate/{room_id}")
    async def communicate(
        room_id: str,
        ws: WebSocket,
        role: str = "user",
    ) -> None:
        role_key = (role or "").lower()
        if role_key not in {"user", "scammer"}:
            await ws.close(code=4000)
            return

        await ws.accept()
        room = await _get_room(room_id)
        client = await room.join(ws, role=role_key)

        await ws.send_json(
            {"event": "ready", "client_id": client.client_id, "role": client.role}
        )

        existing_peers = await room.peers(ws)
        if existing_peers:
            await ws.send_json(
                {
                    "event": "peers",
                    "peers": [
                        {"client_id": peer.client_id, "role": peer.role}
                        for peer in existing_peers
                    ],
                }
            )

        await _notify_peers(
            room,
            {
                "event": "peer_joined",
                "client_id": client.client_id,
                "role": client.role,
            },
            exclude=ws,
        )

        audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        pending_audio = bytearray()
        stream_closed = False
        flagged_emitted = False

        async def audio_chunk_stream():
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                yield chunk

        async def flag_worker():
            nonlocal pending_audio, flagged_emitted
            try:
                async for flagged in audio_service.process_stream(
                    audio_chunk_stream(), role=client.role
                ):
                    payload = bytes(pending_audio)
                    pending_audio = bytearray()
                    if payload:
                        await _broadcast_flagged_audio(room, client, payload, flagged)
                        flagged_emitted = True
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "Failed to process audio stream for client %s", client.client_id
                )

        flag_task = asyncio.create_task(flag_worker())

        try:
            while True:
                message = await ws.receive()
                message_type = message.get("type")
                if message_type == "websocket.disconnect":
                    break

                binary = message.get("bytes")
                if binary is not None:
                    pending_audio.extend(binary)
                    await _broadcast_raw_audio(room, client, binary)
                    await audio_queue.put(binary)
                    continue

                text = message.get("text")
                if text is not None:
                    handled = False
                    if text:
                        try:
                            payload = json.loads(text)
                        except json.JSONDecodeError:
                            payload = None
                        if isinstance(payload, dict) and payload.get("event") == "end":
                            stream_closed = True
                            await audio_queue.put(None)
                            handled = True
                            break
                    if not handled:
                        await _broadcast_text(room, ws, text)
                    continue
        except WebSocketDisconnect:
            pass
        finally:
            if not stream_closed:
                await audio_queue.put(None)

            try:
                await flag_task
            except asyncio.CancelledError:
                pass

            if pending_audio and not flagged_emitted:
                await _broadcast_flagged_audio(
                    room,
                    client,
                    bytes(pending_audio),
                    FlaggedTranscript(text="", flagged=False, is_final=True),
                )

            departed = await room.leave(ws)
            departed_client = departed or client
            await _notify_peers(
                room,
                {
                    "event": "peer_left",
                    "client_id": departed_client.client_id,
                    "role": departed_client.role,
                },
            )
            await _cleanup_room(room_id, room)

    return router
