import asyncio
import base64
import json

import websockets

RAILWAY_WS_URL = (
    "wss://backendanonymaudio-production.up.railway.app/ws/communicate/demo"
)


async def client_simulation(role: str, send_chunks: list[bytes]):
    url = f"{RAILWAY_WS_URL}?role={role}"
    async with websockets.connect(url) as ws:
        # Receive ready message
        ready = await ws.recv()
        print(f"[{role}] Ready:", ready)

        # Receive existing peers (if any)
        try:
            peers = await asyncio.wait_for(ws.recv(), timeout=1)
            print(f"[{role}] Peers:", peers)
        except asyncio.TimeoutError:
            pass

        # Send audio chunks
        for chunk in send_chunks:
            await ws.send(chunk)
            print(f"[{role}] Sent audio chunk: {len(chunk)} bytes")
            try:
                # Receive broadcast from peers
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                if data.get("event") == "audio":
                    audio_bytes = base64.b64decode(data["audio_b64"])
                    print(
                        f"[{role}] Received audio from {data['client_id']} (flagged={data['flagged']}), {len(audio_bytes)} bytes"
                    )
            except asyncio.TimeoutError:
                pass

        # End the stream
        await ws.send(json.dumps({"event": "end"}))
        print(f"[{role}] Sent end event")

        # Wait a bit to receive final messages
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                print(f"[{role}] Final message:", msg)
        except asyncio.TimeoutError:
            print(f"[{role}] Done")


async def main():
    user_chunks = [b"\x01\x02" * 10]
    scammer_chunks = [b"\x03\x04" * 12]

    await asyncio.gather(
        client_simulation("user", user_chunks),
        client_simulation("scammer", scammer_chunks),
    )


if __name__ == "__main__":
    asyncio.run(main())
