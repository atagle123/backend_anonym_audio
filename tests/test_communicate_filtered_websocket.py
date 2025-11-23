import json
from base64 import b64decode
from typing import AsyncIterable, AsyncIterator, List

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.communicate_websocket import (
    DEFAULT_SILENCE_MP3,
    create_communicate_filtered_router,
)
from backend.services.audio_flag_service import FlaggedTranscript


class FakeAudioFlagService:
    def __init__(self) -> None:
        self.calls: List[bytes] = []

    async def process_stream(
        self, audio_chunks: AsyncIterable[bytes], role: str
    ) -> AsyncIterator[FlaggedTranscript]:
        async for chunk in audio_chunks:
            payload = bytes(chunk)
            self.calls.append(payload)
            yield FlaggedTranscript(text=f"len:{len(payload)}", flagged=False, is_final=True)


class FakeAudioAnonymizerService:
    def __init__(self) -> None:
        self.calls: List[List[bytes]] = []

    async def anonymize_stream(self, audio_chunks: AsyncIterable[bytes]) -> bytes:
        collected: List[bytes] = []
        async for chunk in audio_chunks:
            collected.append(bytes(chunk))
        self.calls.append(collected)
        return b"ANON" + b"".join(collected)


def test_communication_filtered_waits_for_anonymizer_and_targets_scammers() -> None:
    flag_service = FakeAudioFlagService()
    anonymizer_service = FakeAudioAnonymizerService()

    app = FastAPI()
    app.include_router(create_communicate_filtered_router(flag_service, anonymizer_service))

    with TestClient(app) as client:
        with client.websocket_connect("/ws/communication-filtered/demo?role=user") as ws_user:
            ready_user = ws_user.receive_json()
            assert ready_user["event"] == "ready"
            assert ready_user["role"] == "user"
            client_user = ready_user["client_id"]

            with client.websocket_connect(
                "/ws/communication-filtered/demo?role=scammer"
            ) as ws_scammer:
                ready_scammer = ws_scammer.receive_json()
                assert ready_scammer["event"] == "ready"
                assert ready_scammer["role"] == "scammer"
                client_scammer = ready_scammer["client_id"]
                assert client_scammer != client_user

                peers_payload = ws_scammer.receive_json()
                assert peers_payload["event"] == "peers"
                assert {
                    "client_id": client_user,
                    "role": "user",
                } in peers_payload["peers"]

                joined_event = ws_user.receive_json()
                assert joined_event == {
                    "event": "peer_joined",
                    "client_id": client_scammer,
                    "role": "scammer",
                }

                audio_chunk = b"\x01\x02" * 5
                ws_user.send_bytes(audio_chunk)

                ws_user.send_text(json.dumps({"event": "end"}))

                anonymized_event = ws_scammer.receive_json()
                assert anonymized_event["event"] == "audio_anonymized"
                assert anonymized_event["client_id"] == client_user
                assert anonymized_event["role"] == "user"
                assert anonymized_event["flagged"] is False
                assert anonymized_event["is_final"] is True
                assert anonymized_event["transcript"] == "len:10"
                assert anonymized_event["audio_format"] == "mp3"
                assert b64decode(anonymized_event["audio_b64"]) == b"ANON" + audio_chunk

                # Audio coming from the scammer is ignored by design.
                ws_scammer.send_bytes(b"\x03\x04")

            peer_left = ws_user.receive_json()
            assert peer_left == {
                "event": "peer_left",
                "client_id": client_scammer,
                "role": "scammer",
            }

    assert flag_service.calls == [b"\x01\x02" * 5]
    assert anonymizer_service.calls == [[b"\x01\x02" * 5]]


def test_communication_filtered_censors_flagged_audio() -> None:
    class AlwaysFlaggingService(FakeAudioFlagService):
        async def process_stream(
            self, audio_chunks: AsyncIterable[bytes], role: str
        ) -> AsyncIterator[FlaggedTranscript]:
            async for chunk in audio_chunks:
                payload = bytes(chunk)
                self.calls.append(payload)
                yield FlaggedTranscript(text="flagged content", flagged=True, is_final=True)

    flag_service = AlwaysFlaggingService()
    anonymizer_service = FakeAudioAnonymizerService()

    app = FastAPI()
    app.include_router(create_communicate_filtered_router(flag_service, anonymizer_service))

    with TestClient(app) as client:
        with client.websocket_connect("/ws/communication-filtered/demo?role=user") as ws_user:
            ready_user = ws_user.receive_json()
            client_user = ready_user["client_id"]

            with client.websocket_connect(
                "/ws/communication-filtered/demo?role=scammer"
            ) as ws_scammer:
                ws_scammer.receive_json()  # ready
                ws_scammer.receive_json()  # peers
                ws_user.receive_json()  # peer_joined

                ws_user.send_bytes(b"\x0a\x0b" * 4)
                ws_user.send_text(json.dumps({"event": "end"}))

                anonymized_event = ws_scammer.receive_json()
                assert anonymized_event["event"] == "audio_anonymized"
                assert anonymized_event["client_id"] == client_user
                assert anonymized_event["flagged"] is True
                assert anonymized_event["audio_format"] == "mp3"
                assert anonymized_event["transcript"] == "flagged content"
                assert b64decode(anonymized_event["audio_b64"]) == DEFAULT_SILENCE_MP3

    assert flag_service.calls == [b"\x0a\x0b" * 4]
