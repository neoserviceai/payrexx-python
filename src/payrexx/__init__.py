"""payrexx — a Python client for the Payrexx payment API.

Payrexx publishes official SDKs for PHP, Node and C#, but none for Python. This
library fills that gap. Its coverage is modelled on the official
`PHP SDK <https://github.com/payrexx/payrexx-php>`_, which documents more of the
API surface than the REST reference does — including whole resources, dozens of
gateway fields, three undocumented transaction statuses, and the fact that
``cancel`` is a ``DELETE`` while every sibling action is a ``POST``.

It also encodes the behaviours that are easy to get wrong, each verified against a
live account rather than inferred from the docs:

- ``instance`` is required on *every* endpoint, ``/ecr/*`` included, and its
  absence surfaces as an opaque ``422``. The client always sends it.
- List parameters must use PHP's indexed bracket form (``pm[0]=twint``). The other
  spellings return ``200 OK`` and are silently ignored.
- Nothing is idempotent. Identical requests create duplicate resources, so POSTs
  are never retried automatically.
- Webhook signatures are lowercase-hex HMAC-SHA256 over the raw body, with the key
  as UTF-8 text.

Quick start::

    from payrexx import PayrexxClient

    client = PayrexxClient(instance="my-shop", api_secret="…")

    gateway = client.gateway.create(
        amount=1500,  # CHF 15.00, in cents
        currency="CHF",
        reference_id="ORDER-1001",
        payment_methods=["twint"],  # encoded as pm[0]=twint
        success_redirect_url="https://example.com/thanks",
    )
    print(gateway.link)  # send the shopper here

Receiving the webhook::

    from payrexx import parse_webhook

    event = parse_webhook(raw_body, headers=headers, signing_key=key)
    if event.transaction and event.transaction.status == "confirmed":
        settle(event.transaction.reference_id)
"""

from payrexx.client import (
    API_VERSION,
    ECR_API_VERSION,
    MERCHANT_API_VERSION,
    PayrexxClient,
)
from payrexx.enums import (
    Currency,
    EcrPaymentMethod,
    EcrPaymentStatus,
    Interval,
    Mode,
    PaymentMethod,
    SubscriptionStatus,
    TransactionStatus,
    TransactionType,
)
from payrexx.errors import (
    AuthenticationError,
    InvalidRequestError,
    MissingInstanceError,
    NotFoundError,
    PayrexxAPIError,
    PayrexxError,
    PayrexxTransportError,
    RateLimitError,
    ServerError,
    TerminalNotFoundError,
    TerminalNotPairedError,
    WebhookSignatureError,
)
from payrexx.models import (
    AuthToken,
    Bill,
    Design,
    EcrPayment,
    Gateway,
    Invoice,
    Page,
    PaymentMethodInfo,
    PaymentProvider,
    Payout,
    QrCode,
    Subscription,
    TerminalPairing,
    Transaction,
)
from payrexx.webhook import (
    SIGNATURE_HEADER,
    WebhookEvent,
    compute_signature,
    parse_webhook,
    verify_signature,
)

__version__ = "0.4.0"

__all__ = [
    "__version__",
    # Client
    "PayrexxClient",
    "API_VERSION",
    "MERCHANT_API_VERSION",
    "ECR_API_VERSION",
    # Models
    "Gateway",
    "Transaction",
    "EcrPayment",
    "PaymentProvider",
    "TerminalPairing",
    "Subscription",
    "Invoice",
    "Page",
    "Bill",
    "Payout",
    "QrCode",
    "Design",
    "PaymentMethodInfo",
    "AuthToken",
    # Enums
    "TransactionStatus",
    "TransactionType",
    "PaymentMethod",
    "EcrPaymentMethod",
    "EcrPaymentStatus",
    "SubscriptionStatus",
    "Currency",
    "Interval",
    "Mode",
    # Webhook
    "parse_webhook",
    "verify_signature",
    "compute_signature",
    "WebhookEvent",
    "SIGNATURE_HEADER",
    # Errors
    "PayrexxError",
    "PayrexxTransportError",
    "AuthenticationError",
    "InvalidRequestError",
    "MissingInstanceError",
    "NotFoundError",
    "TerminalNotFoundError",
    "TerminalNotPairedError",
    "RateLimitError",
    "PayrexxAPIError",
    "ServerError",
    "WebhookSignatureError",
]
