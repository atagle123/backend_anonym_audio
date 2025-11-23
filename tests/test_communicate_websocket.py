from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.communicate_websocket import create_communicate_router


def test_communicate_websocket_relays_audio_between_two_peers() -> None:
    app = FastAPI()
    app.include_router(create_communicate_router())

    with TestClient(app) as client:
        with client.websocket_connect("/ws/communicate/demo") as ws_a:
            ready_a = ws_a.receive_json()
            assert ready_a["event"] == "ready"
            client_a = ready_a["client_id"]

            with client.websocket_connect("/ws/communicate/demo") as ws_b:
                ready_b = ws_b.receive_json()
                assert ready_b["event"] == "ready"
                client_b = ready_b["client_id"]
                assert client_b != client_a

                peers_b = ws_b.receive_json()
                assert peers_b["event"] == "peers"
                assert client_a in peers_b["client_ids"]

                peer_joined = ws_a.receive_json()
                assert peer_joined == {"event": "peer_joined", "client_id": client_b}

                audio_chunk_a = b"\x01\x02" * 10
                ws_a.send_bytes(audio_chunk_a)
                assert ws_b.receive_bytes() == audio_chunk_a

                audio_chunk_b = b"\x03\x04" * 12
                ws_b.send_bytes(audio_chunk_b)
                assert ws_a.receive_bytes() == audio_chunk_b

                control_message = '{"event": "end"}'
                ws_b.send_text(control_message)
                assert ws_a.receive_text() == control_message

            peer_left = ws_a.receive_json()
            assert peer_left == {"event": "peer_left", "client_id": client_b}

