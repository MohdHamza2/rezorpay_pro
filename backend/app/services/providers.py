"""
Provider adapters for Phase 5 comms (Wave 26: Resend email API).

Adapters are thin async wrappers over each provider's public HTTP API
(``httpx.AsyncClient``). Services depend on the adapter, never on HTTP
directly. ``COMMS_DRY_RUN`` (default true) short-circuits every call so CI
and tests never reach a provider; the caller marks simulated rows
``simulated=True`` so they can never be confused with real delivery.

Security: never log tokens, keys, secrets, message bodies, or full recipient
PII. Only ids, status transitions, and redacted error classes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ProviderResult:
    """Uniform provider outcome. ``message_id`` is the provider's own id
    (``resend_message_id`` / future ``wa_message_id``); ``error`` is a
    redacted description (status code / error class name), never a body."""

    message_id: Optional[str]
    ok: bool
    error: Optional[str]

    @staticmethod
    def success(message_id: str) -> "ProviderResult":
        return ProviderResult(message_id=message_id, ok=True, error=None)

    @staticmethod
    def failure(error: str) -> "ProviderResult":
        return ProviderResult(message_id=None, ok=False, error=error)


class ResendProvider:
    """Resend transactional-email adapter (`POST https://api.resend.com/emails`).

    Dry-run (`COMMS_DRY_RUN=true`) or a missing key is treated as disabled and
    returns a simulated success with an empty message id; the service marks
    the row ``simulated=True`` in that case.
    """

    SEND_URL = "https://api.resend.com/emails"
    TIMEOUT_SECONDS = 15.0

    def __init__(self) -> None:
        self._settings = get_settings()

    def enabled(self) -> bool:
        return not self._settings.COMMS_DRY_RUN and bool(self._settings.RESEND_API_KEY)

    async def send(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body_html: str,
        bcc: Optional[list[str]] = None,
    ) -> ProviderResult:
        if not self.enabled():
            return ProviderResult.success("")
        payload: dict = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": body_html,
        }
        if bcc:
            payload["bcc"] = list(bcc)
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.SEND_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._settings.RESEND_API_KEY}"
                    },
                )
            if response.status_code >= 400:
                logger.warning(
                    "resend_http_error",
                    extra={"status_code": response.status_code},
                )
                return ProviderResult.failure(f"http_{response.status_code}")
            data = response.json()
            message_id = (data or {}).get("id")
            if not message_id:
                return ProviderResult.failure("missing_message_id")
            return ProviderResult.success(message_id)
        except httpx.HTTPError as exc:
            logger.warning(
                "resend_network_error",
                extra={"error_class": type(exc).__name__},
            )
            return ProviderResult.failure("network_error")


resend_provider = ResendProvider()
