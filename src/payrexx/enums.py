"""Enumerations for Payrexx transaction states, channels and payment methods.

All values derive from ``str``, so they compare equal to the raw API strings and
can be dropped straight into request payloads. Unknown values coming back from
the API are never coerced — see :meth:`TransactionStatus.parse`.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class TransactionStatus(_StrEnum):
    """The thirteen states a Payrexx transaction can report.

    Sourced from the transaction webhook reference. ``PARTIALLY_REFUNDED`` uses a
    hyphen and ``REFUND_PENDING`` an underscore — that inconsistency is Payrexx's,
    not a typo here.
    """

    WAITING = "waiting"
    """Order placed, nothing captured yet."""

    CONFIRMED = "confirmed"
    """Payment succeeded."""

    CANCELLED = "cancelled"
    """Shopper aborted."""

    DECLINED = "declined"
    """Failed 3-D Secure, or refused by the issuing bank."""

    AUTHORIZED = "authorized"
    """Tokenisation succeeded."""

    RESERVED = "reserved"
    """Reservation succeeded, awaiting capture."""

    REFUNDED = "refunded"
    """Fully refunded."""

    PARTIALLY_REFUNDED = "partially-refunded"
    """Partially refunded; read the real figure from ``invoice.refundedAmount``."""

    REFUND_PENDING = "refund_pending"
    """Refund is being processed."""

    CHARGEBACK = "chargeback"
    """Cardholder pulled the money back."""

    DISPUTED = "disputed"
    """A dispute was opened on this transaction."""

    ERROR = "error"
    """Something went wrong during payment."""

    EXPIRED = "expired"
    """Abandoned through inactivity."""

    @classmethod
    def parse(cls, raw: str | None) -> TransactionStatus | str | None:
        """Return the matching member, or ``raw`` unchanged when unrecognised.

        Deliberately lenient: a status Payrexx adds later must not crash a payment
        flow. Callers that need certainty should check ``isinstance(..., cls)``.
        """
        if raw is None:
            return None
        try:
            return cls(raw)
        except ValueError:
            return raw

    @property
    def is_final(self) -> bool:
        """True when no further state change is expected without a new action."""
        return self in _FINAL_STATUSES

    @property
    def is_successful(self) -> bool:
        """True when the money reached the merchant."""
        return self is TransactionStatus.CONFIRMED


_FINAL_STATUSES = frozenset(
    {
        TransactionStatus.CONFIRMED,
        TransactionStatus.CANCELLED,
        TransactionStatus.DECLINED,
        TransactionStatus.REFUNDED,
        TransactionStatus.CHARGEBACK,
        TransactionStatus.ERROR,
        TransactionStatus.EXPIRED,
    }
)


class TransactionType(_StrEnum):
    """How a transaction was collected.

    Carried by the ``type`` field of the transaction webhook, which makes a single
    webhook endpoint enough to route events to the right channel.
    """

    ECOMMERCE = "E-Commerce"
    POS_TERMINAL = "POS-Terminal"
    TAP_TO_PAY = "Tap to Pay"


class Mode(_StrEnum):
    """Whether the transaction ran against test or live credentials."""

    TEST = "TEST"
    LIVE = "LIVE"


class PaymentMethod(_StrEnum):
    """Payment method identifiers accepted by the ``pm`` filter.

    Only a subset is enabled on any given account; read the live list from
    :meth:`payrexx.resources.payment_provider.PaymentProviderResource.list`
    (``activePaymentMethods``) rather than assuming.
    """

    MASTERCARD = "mastercard"
    VISA = "visa"
    AMERICAN_EXPRESS = "american-express"
    DINERS_CLUB = "diners-club"
    DISCOVER = "discover"
    APPLE_PAY = "apple-pay"
    GOOGLE_PAY = "google-pay"
    SAMSUNG_PAY = "samsung-pay"
    TWINT = "twint"
    POST_FINANCE_PAY = "post-finance-pay"
    BANK_TRANSFER = "bank-transfer"
    PAY_BY_BANK = "pay-by-bank"
    INVOICE = "invoice"
    REKA = "reka"
    KLARNA = "klarna"
    IDEAL = "ideal"
    EPS = "eps"
    BANCONTACT = "bancontact"
    PRZELEWY24 = "przelewy24"
    ALIPAY = "alipay"
    WECHAT_PAY = "wechat-pay"
    CRYPTO = "crypto"


class EcrPaymentMethod(_StrEnum):
    """Payment methods selectable on a POS terminal payment request.

    Leaving it unset makes the terminal show its own chooser.
    """

    CARD = "card"
    TWINT = "twint"
