"""Exception hierarchy for the Payrexx API.

Every error raised by this library derives from `PayrexxError`, so callers
can catch a single type. Subclasses map to the HTTP status codes Payrexx actually
returns, observed against a live account:

- ``403`` with ``"The API secret is not correct."`` → `AuthenticationError`
- ``422 Unprocessable Content`` → `InvalidRequestError` (very often a
  missing ``instance`` query parameter — see `MissingInstanceError`)
- ``404`` with ``"Terminal not found"`` → `TerminalNotFoundError`
- ``405``/``403`` after ~600 requests per 5 minutes → `RateLimitError`
"""

from __future__ import annotations

from typing import Any


class PayrexxError(Exception):
    """Base class for every error raised by this library."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: dict[str, Any] | None = None,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}
        self.method = method
        self.path = path

    def __str__(self) -> str:
        bits = [self.message]
        if self.status_code is not None:
            bits.append(f"(HTTP {self.status_code})")
        if self.method and self.path:
            bits.append(f"on {self.method} {self.path}")
        return " ".join(bits)


class PayrexxTransportError(PayrexxError):
    """The request never produced an HTTP response (DNS, TLS, timeout, reset).

    Important for POS work: a transport error means the outcome is *unknown*, not
    failed. Payrexx exposes no idempotency key, so blindly retrying a terminal
    payment can charge the customer twice. Read the payment back instead.
    """


class AuthenticationError(PayrexxError):
    """The API secret was rejected (HTTP 403)."""


class InvalidRequestError(PayrexxError):
    """The request was malformed or incomplete (HTTP 400/422)."""


class MissingInstanceError(InvalidRequestError):
    """The ``instance`` query parameter was absent.

    Payrexx answers ``422 Unprocessable Content`` with an empty ``reason`` and a
    generic message that never names the missing parameter. Since this library
    injects ``instance`` on every call, hitting this usually means the client was
    built without an instance name.
    """


class NotFoundError(PayrexxError):
    """The addressed resource does not exist (HTTP 404)."""


class TerminalNotFoundError(NotFoundError):
    """No POS terminal matches this serial number.

    Also what Payrexx returns for a terminal that exists but is not paired with
    this account, so it does not by itself prove the serial is wrong.
    """


class RateLimitError(PayrexxError):
    """The rate limit was exceeded.

    Payrexx allows roughly 600 requests per 5 minutes per account, enforced by a
    WAF that first answers ``405`` and then ``403`` if the caller keeps going.
    """


class PayrexxAPIError(PayrexxError):
    """Payrexx answered ``{"status": "error"}`` over an otherwise fine HTTP call."""


class ServerError(PayrexxError):
    """Payrexx failed on its side (HTTP 5xx)."""


class WebhookSignatureError(PayrexxError):
    """The ``X-Webhook-Signature`` header did not match the computed HMAC."""
