#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the project root is importable when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.Notifier.service import TwilioClient
from backend.services.audio_flag_service import FlaggedTranscript
from backend.services.notification import TwilioNotifier

REQUIRED_ENV_VARS = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_NUMBER",
    "TWILIO_WHATSAPP_NUMBER",
    "TWILIO_ALERT_TO_NUMBER",
    "TWILIO_ALERT_WHATSAPP_TO",
    "TWILIO_TWIML_URL",
]


def _load_environment(env_file: str | None) -> None:
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()


def _collect_configuration() -> dict[str, str]:
    config = {key: os.getenv(key, "").strip() for key in REQUIRED_ENV_VARS}
    missing = [key for key, value in config.items() if not value]
    if missing:
        missing_fmt = ", ".join(missing)
        raise SystemExit(
            f"Missing required Twilio configuration in environment: {missing_fmt}"
        )

    message_template = os.getenv(
        "TWILIO_ALERT_MESSAGE", "Se detectó un posible fraude: {text}"
    )
    config["TWILIO_ALERT_MESSAGE"] = message_template
    return config


def _build_notifier(config: dict[str, str]) -> TwilioNotifier:
    twilio_client = TwilioClient(
        account_sid=config["TWILIO_ACCOUNT_SID"],
        auth_token=config["TWILIO_AUTH_TOKEN"],
        twilio_number=config["TWILIO_NUMBER"],
        twilio_whatsapp=config["TWILIO_WHATSAPP_NUMBER"],
    )
    return TwilioNotifier(
        twilio=twilio_client,
        phone_target=config["TWILIO_ALERT_TO_NUMBER"],
        whatsapp_target=config["TWILIO_ALERT_WHATSAPP_TO"],
        twiml_url=config["TWILIO_TWIML_URL"],
        message_template=config["TWILIO_ALERT_MESSAGE"],
    )


async def _send_alert(notifier: TwilioNotifier, text: str, flagged: bool) -> None:
    transcript = FlaggedTranscript(text=text, flagged=flagged, is_final=True)
    await notifier.notify_flagged(transcript)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trigger Twilio notifications using the configured environment."
    )
    parser.add_argument(
        "--text",
        default="Alerta generada manualmente desde la herramienta de pruebas.",
        help="Text included in the alert message template (default: %(default)s).",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Optional path to a .env file. Defaults to .env in the project root.",
    )
    parser.add_argument(
        "--no-flag",
        action="store_true",
        help="Mark the transcript segment as not flagged (defaults to flagged).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    env_file = args.env_file
    if env_file:
        env_path = Path(env_file)
        if not env_path.is_file():
            raise SystemExit(f"Specified env file does not exist: {env_file}")

    _load_environment(env_file)
    config = _collect_configuration()
    notifier = _build_notifier(config)

    flagged = not args.no_flag
    try:
        asyncio.run(_send_alert(notifier, args.text, flagged))
    except Exception as exc:
        raise SystemExit(f"Failed to send Twilio notifications: {exc}") from exc

    print("Twilio notifications sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
