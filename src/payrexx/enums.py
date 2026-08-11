"""Enumerations for Payrexx transaction states, channels and payment methods.

All values derive from ``str``, so they compare equal to the raw API strings and
can be dropped straight into request payloads. Unknown values coming back from
the API are never coerced — see `TransactionStatus.parse`.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class TransactionStatus(_StrEnum):
    r"""The states a Payrexx transaction can report.

    Sixteen of them, from the union of two sources that disagree:

    - the transaction webhook reference documents thirteen, including ``chargeback``
    - the official PHP SDK's ``Models\\Response\\Transaction`` constants document
      fifteen, including ``initiated``, ``insecure`` and ``uncaptured`` — which
      appear in no documentation — but **omit** ``chargeback``

    Both sources are therefore incomplete, which is the whole reason
    `parse` never raises on an unknown value.

    ``PARTIALLY_REFUNDED`` uses a hyphen and ``REFUND_PENDING`` an underscore —
    that inconsistency is Payrexx's, not a typo here.
    """

    WAITING = "waiting"
    """Order placed, nothing captured yet."""

    INITIATED = "initiated"
    """Payment started but not yet submitted. Only in the PHP SDK, undocumented."""

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
    """Cardholder pulled the money back. Documented, but absent from the PHP SDK."""

    DISPUTED = "disputed"
    """A dispute was opened on this transaction."""

    ERROR = "error"
    """Something went wrong during payment."""

    EXPIRED = "expired"
    """Abandoned through inactivity."""

    INSECURE = "insecure"
    """Flagged as insecure — 3-D Secure was unavailable or bypassed.

    Only in the PHP SDK, undocumented. Treat with care: the money may have moved
    while the liability shift did not, so it warrants a human look rather than an
    automatic success.
    """

    UNCAPTURED = "uncaptured"
    """Authorised but never captured; the hold will lapse. Only in the PHP SDK."""

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
        # An authorisation that was never captured is over: the hold lapses and
        # no further event follows.
        TransactionStatus.UNCAPTURED,
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
    [`payrexx.resources.payment_provider.PaymentProviderResource.list`][payrexx.resources.payment_provider.PaymentProviderResource.list]
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

    Note:
        The REST reference spells these lowercase (``"twint"``) while the official
        PHP SDK's own example passes ``'TWINT'``. Which casing the terminal firmware
        actually requires is unverified — no simulator exists and we have no paired
        hardware yet. Send the lowercase form (this enum) and check the result on
        the first real device; if the terminal ignores the pre-selection and shows
        its chooser instead, try uppercase.
    """

    CARD = "card"
    TWINT = "twint"


class Currency(_StrEnum):
    """The four currencies the PHP SDK declares as constants.

    Payrexx accepts other ISO 4217 codes; these are simply the ones its own SDK
    names. Every API call here takes a plain string, so this enum is a convenience,
    not a restriction.
    """

    CHF = "CHF"
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"


class Interval(_StrEnum):
    """Common ISO 8601 durations for subscription intervals.

    Payrexx expects an ISO 8601 duration string such as ``P1M`` (monthly) — the
    format used throughout its own examples. Any valid duration works; these cover
    the usual cases.
    """

    WEEKLY = "P1W"
    MONTHLY = "P1M"
    QUARTERLY = "P3M"
    HALF_YEARLY = "P6M"
    YEARLY = "P1Y"


class SubscriptionStatus(_StrEnum):
    """Subscription lifecycle states.

    Neither the PHP SDK nor the REST reference enumerates these — the SDK types
    ``status`` as a bare string. The values below are those observed in the
    transaction webhook payload, so treat the set as incomplete and compare
    defensively.
    """

    ACTIVE = "active"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
