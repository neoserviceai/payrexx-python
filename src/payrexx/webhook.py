"""Webhook signature verification and payload parsing.

Payrexx fires a webhook on every transaction or subscription status change, and it
covers **all three channels** — the payload's ``type`` field is ``E-Commerce``,
``POS-Terminal`` or ``Tap to Pay``. One endpoint is therefore enough to drive web,
terminal and Tap to Pay state, which is preferable to polling given the ~600
requests / 5 minutes rate limit.

Delivery is retried up to 10 times over 24 hours (first attempt within ~1 minute,
then 15 min, 1 h, 2 h, 4 h, then five daily attempts), and the endpoint must answer
within 20 seconds. Answer ``200`` quickly and do the work asynchronously,
otherwise the retries pile up.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qs

from payrexx.errors import WebhookSignatureError
from payrexx.models import Transaction

SIGNATURE_HEADER = "X-Webhook-Signature"


def compute_signature(raw_body: bytes, signing_key: str) -> str:
    """Compute the expected signature for ``raw_body``.

    Payrexx's scheme has three details that are each easy to get wrong, and each
    produces a mismatch that looks like a bad key:

    1. The HMAC is over the **raw request body**. Never re-serialise the parsed
       JSON first — key order and whitespace would differ.
    2. The signing key is used as **plain UTF-8 text**, not base64-decoded.
    3. The digest is **lowercase hexadecimal**, not base64.
    """
    if isinstance(raw_body, str):  # tolerate a decoded body
        raw_body = raw_body.encode("utf-8")
    return hmac.new(
        signing_key.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()


def verify_signature(raw_body: bytes, signature: str | None, signing_key: str) -> bool:
    """Return whether ``signature`` matches, comparing in constant time."""
    if not signature or not signing_key:
        return False
    expected = compute_signature(raw_body, signing_key)
    return hmac.compare_digest(expected, signature.strip().lower())


def parse_body(raw_body: bytes, content_type: str | None = None) -> dict[str, Any]:
    """Parse a webhook body into a dict.

    Payrexx sends either ``application/json`` or
    ``application/x-www-form-urlencoded`` depending on the account's webhook
    settings, so both are handled. When ``content_type`` is not supplied, JSON is
    attempted first and form decoding is the fallback.
    """
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")

    if content_type and "x-www-form-urlencoded" in content_type.lower():
        return _parse_form(raw_body)

    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _parse_form(raw_body)

    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _parse_form(raw_body: bytes) -> dict[str, Any]:
    flat = parse_qs(raw_body.decode("utf-8", errors="replace"))
    return {k: (v[0] if len(v) == 1 else v) for k, v in flat.items()}


class WebhookEvent:
    """A parsed, optionally verified webhook delivery.

    Attributes:
        transaction: The transaction the event describes, when present.
        payload: The full decoded body.
        signature_valid: ``None`` when no verification was requested.
    """

    __slots__ = ("payload", "transaction", "signature_valid", "raw_body")

    def __init__(
        self,
        payload: dict[str, Any],
        *,
        signature_valid: bool | None = None,
        raw_body: bytes | None = None,
    ) -> None:
        self.payload = payload
        self.signature_valid = signature_valid
        self.raw_body = raw_body

        tx = payload.get("transaction")
        self.transaction = Transaction.from_api(tx) if isinstance(tx, dict) else None

    @property
    def event_id(self) -> str | None:
        """A stable identifier for de-duplicating this delivery.

        Payrexx does not send an event id, so one is derived from the transaction
        uuid and its status. That is stable across the up-to-10 delivery retries
        (same uuid, same status → same id) while still distinguishing genuine state
        changes on the same transaction.

        The residual risk is a legitimate re-emission of an identical status, which
        this would swallow as a duplicate. It is the right trade: swallowing a
        redundant event is harmless, whereas processing a retry twice is not.
        """
        if not self.transaction or not self.transaction.uuid:
            return None
        return f"payrexx_{self.transaction.uuid}_{self.transaction.status}"

    @property
    def channel(self) -> Any:
        """The collection channel — use it to route to the right driver."""
        return self.transaction.type if self.transaction else None

    def __repr__(self) -> str:
        return (
            f"WebhookEvent(event_id={self.event_id!r}, "
            f"channel={self.channel!r}, valid={self.signature_valid!r})"
        )


def parse_webhook(
    raw_body: bytes,
    *,
    headers: dict[str, str] | None = None,
    signing_key: str | None = None,
    require_signature: bool = True,
) -> WebhookEvent:
    """Verify and parse a webhook delivery.

    Args:
        raw_body: The **unmodified** request body.
        headers: Request headers; looked up case-insensitively.
        signing_key: The account's webhook signing key. When omitted, no
            verification happens and ``signature_valid`` stays ``None``.
        require_signature: Raise when verification fails. Set it to ``False`` only
            to inspect a delivery during development — an unverified webhook is
            attacker-controlled input and must not drive a payment state machine.

    Raises:
        WebhookSignatureError: Verification failed while ``require_signature``.
    """
    header_map = {k.lower(): v for k, v in (headers or {}).items()}
    signature = header_map.get(SIGNATURE_HEADER.lower())

    valid: bool | None = None
    if signing_key:
        valid = verify_signature(raw_body, signature, signing_key)
        if not valid and require_signature:
            raise WebhookSignatureError(
                "webhook signature mismatch — verify that the raw body is used "
                "unmodified, that the signing key is treated as UTF-8 text rather "
                "than base64, and that the digest is compared as lowercase hex"
            )

    payload = parse_body(raw_body, header_map.get("content-type"))
    return WebhookEvent(payload, signature_valid=valid, raw_body=raw_body)
