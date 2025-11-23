import asyncio
import base64
import json

import websockets

# Your deployed backend on Railway
RAILWAY_WS_URL = (
    "wss://backendanonymaudio-production.up.railway.app/ws/communicate/demo"
)


async def client(role: str, chunks: list[bytes]):
    """Simulate a peer (user or scammer) connecting and sending audio."""
    url = f"{RAILWAY_WS_URL}?role={role}"

    print(f"\n=== Connecting as {role} ===")

    async with websockets.connect(url) as ws:

        # ---- READY EVENT ----
        ready = await ws.recv()
        print(f"[{role}] READY → {ready}")

        # ---- PEERS LIST ----
        try:
            peers = await asyncio.wait_for(ws.recv(), timeout=1)
            print(f"[{role}] PEERS → {peers}")
        except asyncio.TimeoutError:
            print(f"[{role}] No peers yet")

        # ---- SEND AUDIO ----
        for chunk in chunks:
            await ws.send(chunk)
            print(f"[{role}] Sent chunk ({len(chunk)} bytes)")

            # Try to receive audio forwarded from the other peer
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)

                if data.get("event") == "audio":
                    decoded = base64.b64decode(data["audio_b64"])
                    print(
                        f"[{role}] Received audio → "
                        f"from={data['client_id']} "
                        f"role={data['role']} "
                        f"flagged={data['flagged']} "
                        f"bytes={len(decoded)}"
                    )

            except asyncio.TimeoutError:
                print(f"[{role}] No audio received yet")

        # ---- END STREAM ----
        await ws.send(json.dumps({"event": "end"}))
        print(f"[{role}] Sent END")

        # ---- LISTEN FOR FINAL EVENTS ----
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                print(f"[{role}] Final → {msg}")
        except asyncio.TimeoutError:
            print(f"[{role}] Done")


async def main():
    user_audio = [b"\x01\x02" * 10]  # 20 bytes
    scammer_audio = [b"\x03\x04" * 12]  # 24 bytes

    # Run two peers simultaneously
    await asyncio.gather(
        client("user", user_audio),
        client("scammer", scammer_audio),
    )


if __name__ == "__main__":
    asyncio.run(main())
