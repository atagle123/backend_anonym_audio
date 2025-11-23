from __future__ import annotations

import os

from fastapi import FastAPI
from dotenv import load_dotenv

from backend.FilterService.chileFIlter import ChileScamFilter
from backend.api.audio_flag_websocket import create_audio_flag_router
from backend.Notifier.service import TwilioClient
from backend.services import (
    AudioFlagService,
    ElevenLabsSpeechToTextService,
    NotificationService,
    TwilioNotifier,
)

load_dotenv()


def _build_audio_flag_service() -> AudioFlagService:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Export it before starting the server."
        )

    speech_to_text = ElevenLabsSpeechToTextService(api_key=api_key)
    filter_service = ChileScamFilter()
    return AudioFlagService(speech_to_text, filter_service)


def _build_notifier() -> NotificationService:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID") or os.getenv("ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    env_keys = {
        "TWILIO_ACCOUNT_SID": account_sid,
        "TWILIO_AUTH_TOKEN": auth_token,
        "TWILIO_NUMBER": os.getenv("TWILIO_NUMBER"),
        "TWILIO_WHATSAPP_NUMBER": os.getenv("TWILIO_WHATSAPP_NUMBER"),
        "TWILIO_ALERT_TO_NUMBER": os.getenv("TWILIO_ALERT_TO_NUMBER"),
        "TWILIO_ALERT_WHATSAPP_TO": os.getenv("TWILIO_ALERT_WHATSAPP_TO"),
        "TWILIO_TWIML_URL": os.getenv("TWILIO_TWIML_URL"),
    }

    missing = [key for key, value in env_keys.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing Twilio configuration: {}".format(", ".join(missing))
        )

    twilio_client = TwilioClient(
        account_sid=env_keys["TWILIO_ACCOUNT_SID"],
        auth_token=env_keys["TWILIO_AUTH_TOKEN"],
        twilio_number=env_keys["TWILIO_NUMBER"],
        twilio_whatsapp=env_keys["TWILIO_WHATSAPP_NUMBER"],
    )

    message_template = os.getenv(
        "TWILIO_ALERT_MESSAGE", "Se detectó un posible fraude: {text}"
    )

    return TwilioNotifier(
        twilio=twilio_client,
        phone_target=env_keys["TWILIO_ALERT_TO_NUMBER"],
        whatsapp_target=env_keys["TWILIO_ALERT_WHATSAPP_TO"],
        twiml_url=env_keys["TWILIO_TWIML_URL"],
        message_template=message_template,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Audio Flag Service", version="0.1.0")
    audio_flag_service = _build_audio_flag_service()
    notifier = _build_notifier()
    app.include_router(create_audio_flag_router(audio_flag_service, notifier))
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
