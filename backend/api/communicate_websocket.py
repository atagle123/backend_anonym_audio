from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

LOGGER = logging.getLogger(__name__)


class Room:
    """Manage the set of active websocket connections for a room."""

    def __init__(self) -> None:
        self._clients: Dict[int, Tuple[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def join(self, ws: WebSocket) -> str:
        client_id = uuid.uuid4().hex
        async with self._lock:
            self._clients[id(ws)] = (client_id, ws)
        return client_id

    async def leave(self, ws: WebSocket) -> Optional[str]:
        async with self._lock:
            entry = self._clients.pop(id(ws), None)
        return entry[0] if entry else None

    async def peers(self, ws: WebSocket) -> List[Tuple[str, WebSocket]]:
        async with self._lock:
            return [
                (client_id, client_ws)
                for key, (client_id, client_ws) in self._clients.items()
                if key != id(ws)
            ]

    async def clients(self) -> List[Tuple[str, WebSocket]]:
        async with self._lock:
            return list(self._clients.values())

    async def is_empty(self) -> bool:
        async with self._lock:
            return not self._clients


_rooms: Dict[str, Room] = {}
_rooms_lock = asyncio.Lock()


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


async def _broadcast_bytes(
    room: Room, sender: WebSocket, payload: bytes
) -> None:
    peers = await room.peers(sender)
    if not peers:
        return
    tasks = [peer_ws.send_bytes(payload) for _, peer_ws in peers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for (peer_id, _), result in zip(peers, results):
        if isinstance(result, Exception):
            LOGGER.warning("Broadcast to peer %s failed: %s", peer_id, result)


async def _broadcast_text(
    room: Room, sender: WebSocket, payload: str
) -> None:
    peers = await room.peers(sender)
    if not peers:
        return
    tasks = [peer_ws.send_text(payload) for _, peer_ws in peers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for (peer_id, _), result in zip(peers, results):
        if isinstance(result, Exception):
            LOGGER.warning("Broadcast to peer %s failed: %s", peer_id, result)


async def _notify_peers(
    room: Room, payload: dict, exclude: Optional[WebSocket] = None
) -> None:
    clients = await room.clients()
    if not clients:
        return
    tasks = []
    recipients: List[Tuple[str, WebSocket]] = []
    for peer_id, ws in clients:
        if exclude is not None and ws is exclude:
            continue
        recipients.append((peer_id, ws))
        tasks.append(ws.send_json(payload))

    if not tasks:
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for (peer_id, _), result in zip(recipients, results):
        if isinstance(result, Exception):
            LOGGER.warning("Notification to peer %s failed: %s", peer_id, result)


def create_communicate_router() -> APIRouter:
    """
    Register a websocket endpoint that relays binary audio frames between peers.

    Path: `/ws/communicate/{room_id}`
    Notes:
        - Peers join a logical room identified by `room_id`.
        - Binary frames are forwarded losslessly to every other peer.
        - Text frames are forwarded as-is so clients can reuse out-of-band control
          messages (for example, `{"event": "end"}`).
        - Lifecycle events are emitted to all peers (`peer_joined`, `peer_left`).
    """

    router = APIRouter()

    @router.websocket("/ws/communicate/{room_id}")
    async def communicate(room_id: str, ws: WebSocket) -> None:
        await ws.accept()
        room = await _get_room(room_id)
        client_id = await room.join(ws)

        await ws.send_json({"event": "ready", "client_id": client_id})

        existing_peers = await room.peers(ws)
        if existing_peers:
            await ws.send_json(
                {
                    "event": "peers",
                    "client_ids": [peer_id for peer_id, _ in existing_peers],
                }
            )

        await _notify_peers(
            room, {"event": "peer_joined", "client_id": client_id}, exclude=ws
        )

        try:
            while True:
                message = await ws.receive()
                message_type = message.get("type")
                if message_type == "websocket.disconnect":
                    break

                if (binary := message.get("bytes")) is not None:
                    await _broadcast_bytes(room, ws, binary)
                    continue

                if (text := message.get("text")) is not None:
                    await _broadcast_text(room, ws, text)
        except WebSocketDisconnect:
            pass
        finally:
            await room.leave(ws)
            await _notify_peers(
                room, {"event": "peer_left", "client_id": client_id}
            )
            await _cleanup_room(room_id, room)

    return router
