"""
Provider adapters for Phase 5 comms (Wave 26: Resend email API; Wave 27:
WhatsApp Business Platform via Meta Graph API).

Adapters are thin async wrappers over each provider's public HTTP API
(``httpx.AsyncClient``). Services depend on the adapter, never on HTTP
directly. ``COMMS_DRY_RUN`` (default true) short-circuits every call so CI
and tests never reach a provider; the caller marks simulated rows
``simulated=True`` so they can never be confused with real delivery.

Security: never log tokens, keys, secrets, message bodies, or full recipient
PII. Only ids, status transitions, and redacted error classes. Provider
failures surface NORMALIZED fields only (``provider_code`` /
``provider_category`` / a safe ``error`` string) — never raw response bodies
(Meta errors may embed phone numbers/ids/user data).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ProviderResult:
    """Uniform provider outcome. ``message_id`` is the provider's own id
    (``resend_message_id`` / ``wa_message_id`` / ``media_id``); ``error`` is a
    redacted description (status code / error class name), never a body.
    ``provider_code`` / ``provider_category`` carry normalized provider error
    metadata (never raw bodies)."""

    message_id: Optional[str]
    ok: bool
    error: Optional[str]
    provider_code: Optional[str] = None
    provider_category: Optional[str] = None

    @staticmethod
    def success(message_id: str) -> "ProviderResult":
        return ProviderResult(message_id=message_id, ok=True, error=None)

    @staticmethod
    def failure(
        error: str,
        provider_code: Optional[str] = None,
        provider_category: Optional[str] = None,
    ) -> "ProviderResult":
        return ProviderResult(
            message_id=None,
            ok=False,
            error=error,
            provider_code=provider_code,
            provider_category=provider_category,
        )


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


class WhatsappProvider:
    """Meta WhatsApp Cloud API adapter (Wave 27).

    Base ``https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}`` (verified
    default v25.0, 2026-09-07). Bearer ``WHATSAPP_ACCESS_TOKEN``. Two calls:
    media upload (`POST /{phone_number_id}/media`, form `messaging_product`
    + `file`) and message send (`POST /{phone_number_id}/messages`, JSON
    document/text payload).

    Dry-run (`COMMS_DRY_RUN` or missing token/phone-number) returns a
    simulated success with empty ids; the service marks rows
    ``simulated=True``. Failures are normalized to
    ``(provider_code, provider_category, safe error)`` — raw response bodies
    (which may embed phone numbers / user data) are never persisted or logged.
    """

    BASE_URL = "https://graph.facebook.com"
    TIMEOUT_SECONDS = 20.0

    def __init__(self) -> None:
        self._settings = get_settings()

    def enabled(self) -> bool:
        return (
            not self._settings.COMMS_DRY_RUN
            and bool(self._settings.WHATSAPP_ACCESS_TOKEN)
            and bool(self._settings.WHATSAPP_PHONE_NUMBER_ID)
        )

    async def upload_media(
        self, phone_number_id: str, filename: str, pdf_bytes: bytes
    ) -> ProviderResult:
        if not self.enabled():
            return ProviderResult.success("")
        result = await self._post(
            f"/{phone_number_id}/media",
            data={"messaging_product": "whatsapp"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
        )
        if not result.ok:
            return result
        return ProviderResult.success(result.message_id or "")

    async def send_message(
        self, phone_number_id: str, to_number: str, payload: dict
    ) -> ProviderResult:
        if not self.enabled():
            return ProviderResult.success("")
        return await self._post(f"/{phone_number_id}/messages", json=payload)

    # ---------- internals ----------

    async def _post(
        self,
        path: str,
        *,
        json: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
    ) -> ProviderResult:
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.BASE_URL + f"/{self._settings.WHATSAPP_GRAPH_VERSION}" + path,
                    headers={
                        "Authorization": f"Bearer {self._settings.WHATSAPP_ACCESS_TOKEN}"
                    },
                    json=json,
                    data=data,
                    files=files,
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "whatsapp_network_error",
                extra={"error_class": type(exc).__name__},
            )
            return ProviderResult.failure(
                "network_error",
                provider_code="transport_error",
                provider_category=type(exc).__name__,
            )
        if response.status_code >= 400:
            code, category = self._normalized_error(response)
            logger.warning(
                "whatsapp_http_error",
                extra={"status_code": response.status_code, "code": code},
            )
            return ProviderResult.failure(
                f"http_{response.status_code}",
                provider_code=str(code),
                provider_category=category,
            )
        message_id = self._success_id(response)
        if not message_id:
            return ProviderResult.failure("missing_message_id")
        return ProviderResult.success(message_id)

    @staticmethod
    def _normalized_error(response: httpx.Response) -> Tuple[str, str]:
        """Normalized (code, category); never returns raw message text."""
        try:
            body = response.json()
        except Exception:
            body = {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        code = error.get("code") if isinstance(error, dict) else None
        category = error.get("type", "http") if isinstance(error, dict) else "http"
        return (str(code) if code is not None else f"http_{response.status_code}"), (
            str(category) or "http"
        )

    @staticmethod
    def _success_id(response: httpx.Response) -> str:
        try:
            body = response.json()
        except Exception:
            return ""
        if isinstance(body, dict):
            message_id = body.get("id")
            if message_id:
                return str(message_id)
            messages = body.get("messages")
            if isinstance(messages, list) and messages:
                return str(messages[0].get("id") or "")
        return ""


whatsapp_provider = WhatsappProvider()
