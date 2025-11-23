import json
from base64 import b64decode
from typing import AsyncIterable, AsyncIterator, List, Tuple

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.communicate_websocket import create_communicate_router
from backend.services.audio_flag_service import FlaggedTranscript


class FakeAudioFlagService:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, bytes]] = []

    async def process_stream(
        self, audio_chunks: AsyncIterable[bytes], role: str
    ) -> AsyncIterator[FlaggedTranscript]:
        async for chunk in audio_chunks:
            payload = bytes(chunk)
            self.calls.append((role, payload))
            yield FlaggedTranscript(
                text=f"{role}:{len(payload)}",
                flagged=(role == "scammer"),
                is_final=False,
            )


def test_communicate_websocket_relays_flagged_audio_between_peers() -> None:
    service = FakeAudioFlagService()
    app = FastAPI()
    app.include_router(create_communicate_router(service))

    with TestClient(app) as client:
        with client.websocket_connect("/ws/communicate/demo?role=user") as ws_a:
            ready_a = ws_a.receive_json()
            assert ready_a["event"] == "ready"
            assert ready_a["role"] == "user"
            client_a = ready_a["client_id"]

            with client.websocket_connect("/ws/communicate/demo?role=scammer") as ws_b:
                ready_b = ws_b.receive_json()
                assert ready_b["event"] == "ready"
                assert ready_b["role"] == "scammer"
                client_b = ready_b["client_id"]
                assert client_b != client_a

                peers_b = ws_b.receive_json()
                assert peers_b["event"] == "peers"
                assert {
                    "client_id": client_a,
                    "role": "user",
                } in peers_b["peers"]

                peer_joined = ws_a.receive_json()
                assert peer_joined == {
                    "event": "peer_joined",
                    "client_id": client_b,
                    "role": "scammer",
                }

                audio_chunk_a = b"\x01\x02" * 10
                ws_a.send_bytes(audio_chunk_a)
                audio_event_b = ws_b.receive_json()
                assert audio_event_b["event"] == "audio"
                assert audio_event_b["client_id"] == client_a
                assert audio_event_b["role"] == "user"
                assert audio_event_b["flagged"] is False
                assert audio_event_b["transcript"] == "user:20"
                assert b64decode(audio_event_b["audio_b64"]) == audio_chunk_a

                audio_chunk_b = b"\x03\x04" * 12
                ws_b.send_bytes(audio_chunk_b)
                audio_event_a = ws_a.receive_json()
                assert audio_event_a["event"] == "audio"
                assert audio_event_a["client_id"] == client_b
                assert audio_event_a["role"] == "scammer"
                assert audio_event_a["flagged"] is True
                assert audio_event_a["transcript"] == "scammer:24"
                assert b64decode(audio_event_a["audio_b64"]) == audio_chunk_b

                ws_b.send_text(json.dumps({"event": "end"}))

            peer_left = ws_a.receive_json()
            assert peer_left == {
                "event": "peer_left",
                "client_id": client_b,
                "role": "scammer",
            }

    assert service.calls == [
        ("user", b"\x01\x02" * 10),
        ("scammer", b"\x03\x04" * 12),
    ]

