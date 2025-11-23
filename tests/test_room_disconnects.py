from __future__ import annotations

import asyncio

from starlette.websockets import WebSocketState

from backend.api.communicate_websocket import Room, _broadcast_raw_audio


class FakeWebSocket:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.client_state = WebSocketState.CONNECTED
        self.sent_payloads: list[dict] = []
        self.should_fail = False
        self.closed = False

    async def send_json(self, payload: dict) -> None:
        if self.should_fail:
            self.application_state = WebSocketState.DISCONNECTED
            self.client_state = WebSocketState.DISCONNECTED
            raise RuntimeError('Cannot call "send" once a close message has been sent.')
        self.sent_payloads.append(payload)

    async def send_text(self, payload: str) -> None:
        if self.should_fail:
            self.application_state = WebSocketState.DISCONNECTED
            self.client_state = WebSocketState.DISCONNECTED
            raise RuntimeError('Cannot call "send" once a close message has been sent.')
        self.sent_payloads.append({"text": payload})

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.application_state = WebSocketState.DISCONNECTED
        self.client_state = WebSocketState.DISCONNECTED
        self.closed = True


def test_broadcast_prunes_disconnected_peers_and_notifies_remaining_clients() -> None:
    async def exercise() -> None:
        room = Room()
        sender_ws = FakeWebSocket()
        sender = await room.join(sender_ws, role="user")

        stale_ws = FakeWebSocket()
        await room.join(stale_ws, role="scammer")
        stale_ws.should_fail = True

        await _broadcast_raw_audio(room, sender, b"\x00\x01")

        peers_after = await room.peers(sender_ws)
        assert peers_after == []
        assert stale_ws.closed is True

        assert sender_ws.sent_payloads
        peer_left_events = [
            payload
            for payload in sender_ws.sent_payloads
            if payload.get("event") == "peer_left"
        ]
        assert (
            peer_left_events
        ), "Expected a peer_left notification for remaining clients"

    asyncio.run(exercise())
