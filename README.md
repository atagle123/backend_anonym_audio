## Audio Flagging WebSocket

This service streams PCM16 mono audio (16kHz) to ElevenLabs' Scribe v2 API, filters the emitted transcript with the Chilean scam wordlist, and pushes both the transcript and the flagging result back to the caller.

### Quickstart

1. Install dependencies (the project uses [`uv`](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

2. Export your ElevenLabs token:

   ```bash
   export ELEVENLABS_API_KEY=sk-...
   ```

3. Run the API:

   ```bash
   uv run uvicorn main:app --reload
   ```

4. Connect a WebSocket client to `ws://localhost:8000/ws/audio-flag` and stream:

   - Binary frames: raw PCM16 mono audio chunks (@16kHz).
   - Text frame `{"event": "end"}` when you're done sending audio.

   The server responds with JSON messages such as:

   ```json
   {"event":"transcript","text":"...","flagged":false,"is_final":false}
   {"event":"summary","flagged":true}
   ```

   When a transcript segment is flagged for suspicious content, the server will place a Twilio voice call and send a WhatsApp alert containing the transcript text.

### Environment

Set the following variables before launching the API:

- `ELEVENLABS_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_NUMBER` (voice-enabled Twilio number)
- `TWILIO_WHATSAPP_NUMBER` (WhatsApp-enabled Twilio number)
- `TWILIO_ALERT_TO_NUMBER` (recipient of the voice call)
- `TWILIO_ALERT_WHATSAPP_TO` (recipient of the WhatsApp alert, international format)
- `TWILIO_TWIML_URL` (public URL hosting the TwiML instructions for the call)
- `TWILIO_ALERT_MESSAGE` (optional template, defaults to `"Se detectó un posible fraude: {text}"`)

### Notes

- Low-latency streaming depends on ElevenLabs' `speech-to-text/stream` endpoint. Double-check their latest docs to confirm the protocol details.
- Update the wordlist in `backend/FilterService/chileFIlter.py` to adapt the scam filter for your use case.
