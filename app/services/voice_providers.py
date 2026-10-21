"""Voice Telephony Providers for Calling Agent (Console Mock and Twilio Voice)."""

import os
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger("VoiceProvider")


class BaseVoiceProvider(ABC):
    """Abstract interface for voice call telephony dispatch."""

    @abstractmethod
    def initiate_call(
        self,
        to_phone: str,
        tts_script: str,
        callback_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch outbound automated call."""
        pass


class ConsoleVoiceProvider(BaseVoiceProvider):
    """Simulated voice telephony provider for local development, CI, and test execution."""

    def __init__(self):
        self.call_history: list[Dict[str, Any]] = []

    def initiate_call(
        self,
        to_phone: str,
        tts_script: str,
        callback_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record and simulate outbound voice call."""
        call_sid = f"MOCK_CALL_{uuid.uuid4().hex[:12].upper()}"
        record = {
            "channel": "VOICE_CALL",
            "provider": "CONSOLE_MOCK",
            "call_sid": call_sid,
            "to_phone": to_phone,
            "status": "QUEUED",
            "tts_script": tts_script,
            "callback_url": callback_url,
            "metadata": metadata or {},
        }
        self.call_history.append(record)
        logger.info(f"[VOICE DISPATCH] Outbound Call to {to_phone} | Script: '{tts_script[:60]}...'")
        return record

    def get_history(self) -> list[Dict[str, Any]]:
        return self.call_history


class TwilioVoiceProvider(BaseVoiceProvider):
    """Twilio Voice API provider with graceful fallback to ConsoleVoiceProvider."""

    def __init__(self, fallback: Optional[BaseVoiceProvider] = None):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_phone = os.getenv("TWILIO_PHONE_NUMBER")
        self.fallback = fallback or ConsoleVoiceProvider()

    def initiate_call(
        self,
        to_phone: str,
        tts_script: str,
        callback_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch call via Twilio Voice REST API if configured, or fall back cleanly."""
        if not (self.account_sid and self.auth_token and self.from_phone):
            res = self.fallback.initiate_call(to_phone, tts_script, callback_url, metadata)
            res["fallback"] = True
            res["fallback_reason"] = "Twilio credentials not configured; used ConsoleVoiceProvider."
            return res

        # Production Twilio SDK invocation when credentials are provided
        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            twiml = f"<Response><Say voice='Polly.Aditi'>{tts_script}</Say><Gather numDigits='1' timeout='15'></Gather></Response>"
            call = client.calls.create(
                to=to_phone,
                from_=self.from_phone,
                twiml=twiml,
                status_callback=callback_url,
            )
            return {
                "channel": "VOICE_CALL",
                "provider": "TWILIO",
                "call_sid": call.sid,
                "to_phone": to_phone,
                "status": call.status or "QUEUED",
                "tts_script": tts_script,
                "fallback": False,
            }
        except Exception as exc:
            logger.warning(f"Twilio call failed: {exc}. Falling back to ConsoleVoiceProvider.")
            res = self.fallback.initiate_call(to_phone, tts_script, callback_url, metadata)
            res["fallback"] = True
            res["fallback_reason"] = str(exc)
            return res
