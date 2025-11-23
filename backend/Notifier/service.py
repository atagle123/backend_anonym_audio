from twilio.rest import Client


class TwilioClient:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        twilio_number: str,
        twilio_whatsapp: str = None,
    ):
        """
        :param account_sid: Twilio Account SID
        :param auth_token: Twilio Auth Token
        :param twilio_number: Your Twilio phone number used for call/SMS
        :param twilio_whatsapp: Your Twilio WhatsApp number (starts with 'whatsapp:+1...')
        """
        self.client = Client(account_sid, auth_token)
        self.twilio_number = twilio_number
        self.twilio_whatsapp = twilio_whatsapp

    def create_call(self, to_number: str, twiml_url: str):
        """
        Create a phone call to a given number.
        :param to_number: Destination number, e.g. +56912345678
        :param twiml_url: Public URL containing TwiML instructions
        """
        call = self.client.calls.create(
            to=to_number, from_=self.twilio_number, url=twiml_url
        )
        return call.sid

    def send_sms(self, to_number: str, message: str):
        """
        Send an SMS message via the configured Twilio number.
        :param to_number: Destination number, e.g. +56912345678
        :param message: Text message
        """
        msg = self.client.messages.create(
            body=message, from_=self.twilio_number, to=to_number
        )
        return msg.sid

    def send_whatsapp(self, to_number: str, message: str):
        """
        Send a WhatsApp message.
        :param to_number: WhatsApp target, e.g. +56912345678
        :param message: Text message
        """
        if not self.twilio_whatsapp:
            raise ValueError("Twilio WhatsApp number not configured")

        msg = self.client.messages.create(
            body=message,
            from_=f"whatsapp:{self.twilio_whatsapp}",
            to=f"whatsapp:{to_number}",
        )
        return msg.sid
