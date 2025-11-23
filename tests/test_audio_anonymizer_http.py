import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.audio_anonymizer_http import create_audio_anonymizer_router


class RecordingAnonymizerService:
    def __init__(self) -> None:
        self.chunks = []
        self._synthesis_output_format = "mp3_44100_128"

    async def anonymize_stream(self, audio_chunks):
        collected = []
        async for chunk in audio_chunks:
            collected.append(bytes(chunk))
        self.chunks.append(b"".join(collected))
        return b"ANON" + self.chunks[-1]


def test_anonymize_audio_endpoint_returns_base64_audio() -> None:
    service = RecordingAnonymizerService()
    app = FastAPI()
    app.include_router(create_audio_anonymizer_router(service))
    client = TestClient(app)

    raw_audio = b"\x00\x01\x02"
    audio_b64 = base64.b64encode(raw_audio).decode("ascii")

    response = client.post("/anonymize-audio", json={"audio_b64": audio_b64})
    assert response.status_code == 200

    payload = response.json()
    assert payload["audio_format"] == "mp3_44100_128"
    assert base64.b64decode(payload["audio_b64"]) == b"ANON" + raw_audio
    assert service.chunks == [raw_audio]


def test_anonymize_audio_endpoint_validates_base64() -> None:
    service = RecordingAnonymizerService()
    app = FastAPI()
    app.include_router(create_audio_anonymizer_router(service))
    client = TestClient(app)

    response = client.post("/anonymize-audio", json={"audio_b64": "not-base64"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid base64 audio payload."


def test_anonymize_audio_endpoint_requires_non_empty_audio() -> None:
    service = RecordingAnonymizerService()
    app = FastAPI()
    app.include_router(create_audio_anonymizer_router(service))
    client = TestClient(app)

    empty_audio = base64.b64encode(b"").decode("ascii")
    response = client.post("/anonymize-audio", json={"audio_b64": empty_audio})
    assert response.status_code == 400
    assert response.json()["detail"] == "Audio payload is empty."
