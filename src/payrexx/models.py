"""Typed views over the Payrexx JSON payloads.

Every model keeps the untouched response in ``raw``, so a field this library does
not model yet stays reachable. Parsing is deliberately tolerant: an unexpected or
missing key must never break a payment flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from payrexx.enums import Mode, TransactionStatus, TransactionType


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PaymentProvider:
    """A PSP configured on the account, e.g. ``Payrexx Pay`` (id 44)."""

    id: int | None
    name: str
    payment_methods: tuple[str, ...] = ()
    active_payment_methods: tuple[str, ...] = ()
    available_balance: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PaymentProvider:
        """Build an instance from a Payrexx API payload."""
        return cls(
            id=_as_int(data.get("id")),
            name=data.get("name") or "",
            payment_methods=tuple(data.get("paymentMethods") or ()),
            active_payment_methods=tuple(data.get("activePaymentMethods") or ()),
            available_balance=tuple(data.get("availableBalance") or ()),
            raw=data,
        )

    def supports(self, method: str) -> bool:
        """True when ``method`` is enabled — not merely supported — on this PSP."""
        return str(method) in self.active_payment_methods


@dataclass(frozen=True)
class Gateway:
    """A hosted payment page created through ``POST /Gateway/``."""

    id: int | None
    hash: str
    link: str
    status: TransactionStatus | str | None
    reference_id: str | None
    amount: int | None
    currency: str | None
    created_at: datetime | None
    invoices: tuple[dict[str, Any], ...] = ()
    payment_methods: tuple[str, ...] = ()
    psp: tuple[Any, ...] = ()
    app_link: str | None = None
    transaction_id: int | None = None
    application_fee: int | None = None
    request_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Gateway:
        """Build an instance from a Payrexx API payload."""
        created = _as_int(data.get("createdAt"))
        return cls(
            id=_as_int(data.get("id")),
            hash=data.get("hash") or "",
            link=data.get("link") or "",
            status=TransactionStatus.parse(data.get("status")),
            reference_id=data.get("referenceId"),
            amount=_as_int(data.get("amount")),
            currency=data.get("currency"),
            created_at=(datetime.fromtimestamp(created, tz=timezone.utc) if created else None),
            invoices=tuple(data.get("invoices") or ()),
            payment_methods=tuple(data.get("pm") or ()),
            psp=tuple(data.get("psp") or ()),
            # appLink and transactionId are in the PHP SDK's response model but not
            # in the REST reference. appLink matters for mobile hand-off.
            app_link=data.get("appLink") or None,
            transaction_id=_as_int(data.get("transactionId")),
            application_fee=_as_int(data.get("applicationFee")),
            request_id=data.get("requestId") or None,
            raw=data,
        )

    @property
    def is_paid(self) -> bool:
        """Is paid."""
        return self.status == TransactionStatus.CONFIRMED

    @property
    def filter_was_applied(self) -> bool:
        """Whether Payrexx kept the ``pm`` filter that was requested.

        Payrexx accepts a malformed ``pm`` filter with ``200 OK`` and drops it, so
        the only way to know it took effect is to read ``pm`` back. This library
        always encodes ``pm`` correctly, but the check is exposed for callers that
        want to assert it — the cost of a silently ignored filter is a shopper
        paying by a method the caller never recorded.
        """
        return bool(self.payment_methods)


@dataclass(frozen=True)
class Transaction:
    """A transaction, as returned by the API or delivered by webhook."""

    id: int | None
    uuid: str | None
    status: TransactionStatus | str | None
    amount: int | None
    currency: str | None
    reference_id: str | None
    type: TransactionType | str | None
    mode: Mode | str | None
    time: str | None
    pos_serial_number: str | None = None
    pos_terminal_name: str | None = None
    refundable: bool = False
    partially_refundable: bool = False
    refunded_amount: int | None = None
    payrexx_fee: int | None = None
    original_transaction_uuid: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Transaction:
        """Build an instance from a Payrexx API payload."""
        invoice = data.get("invoice") or {}
        try:
            tx_type: TransactionType | str | None = TransactionType(data["type"])
        except (KeyError, ValueError):
            tx_type = data.get("type")
        try:
            mode: Mode | str | None = Mode(data["mode"])
        except (KeyError, ValueError):
            mode = data.get("mode")

        return cls(
            id=_as_int(data.get("id")),
            uuid=data.get("uuid"),
            status=TransactionStatus.parse(data.get("status")),
            amount=_as_int(data.get("amount")),
            currency=invoice.get("currency") or data.get("currency"),
            # Payrexx exposes referenceId both at the top level and inside invoice;
            # they can disagree when a gateway was edited, so prefer the top level.
            reference_id=data.get("referenceId") or invoice.get("referenceId"),
            type=tx_type,
            mode=mode,
            time=data.get("time"),
            pos_serial_number=data.get("posSerialNumber") or None,
            pos_terminal_name=data.get("posTerminalName") or None,
            refundable=bool(data.get("refundable")),
            partially_refundable=bool(data.get("partiallyRefundable")),
            refunded_amount=_as_int(invoice.get("refundedAmount")),
            payrexx_fee=_as_int(data.get("payrexxFee")),
            original_transaction_uuid=data.get("originalTransactionUuid"),
            metadata=data.get("metadata") or {},
            raw=data,
        )

    @property
    def channel(self) -> TransactionType | str | None:
        """Alias for :attr:`type` — the collection channel of this transaction."""
        return self.type

    @property
    def refundable_amount(self) -> int | None:
        """Amount still refundable, in the smallest currency unit.

        ``None`` when the total is unknown. Returns ``0`` rather than a negative
        figure if Payrexx ever reports a refund larger than the capture.
        """
        if self.amount is None:
            return None
        return max(0, self.amount - (self.refunded_amount or 0))

    @property
    def is_disputed(self) -> bool:
        """True for ``chargeback`` or ``disputed``.

        Worth its own check: neither maps onto a refund, and both usually need an
        operator to look at them rather than an automated state transition.
        """
        return self.status in (TransactionStatus.CHARGEBACK, TransactionStatus.DISPUTED)


@dataclass(frozen=True)
class EcrPayment:
    """A POS terminal payment, from the ``/ecr/*`` endpoints.

    Payrexx's OpenAPI declares ``payment_status`` as a bare string and enumerates
    no values, so :attr:`status` is intentionally left as the raw string. Do not
    hard-code comparisons against guessed values — read the transaction webhook
    (``type == "POS-Terminal"``), whose statuses *are* documented, and treat this
    field as a hint for the UI.
    """

    payment_id: str | None
    status: str | None
    slip: tuple[str, ...] = ()
    serial_number: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any], *, serial_number: str | None = None) -> EcrPayment:
        """Build an instance from a Payrexx API payload."""
        slip = data.get("slip")
        if isinstance(slip, str):
            slip_tuple: tuple[str, ...] = (slip,)
        elif isinstance(slip, dict):
            slip_tuple = tuple(str(v) for v in slip.values())
        else:
            slip_tuple = tuple(slip or ())
        return cls(
            payment_id=data.get("payment_id") or data.get("paymentId"),
            status=data.get("payment_status") or data.get("paymentStatus"),
            slip=slip_tuple,
            serial_number=serial_number,
            raw=data,
        )


@dataclass(frozen=True)
class TerminalPairing:
    """Pairing state of a POS terminal, plus the device configuration it reports.

    The PHP SDK's response model exposes ``status``, ``cashierName``,
    ``configuration`` and ``data`` — the REST reference mentions none of them, so
    the field names below come from the SDK and its ECR example.
    """

    serial_number: str
    paired: bool
    status: str | None = None
    cashier_name: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    raw: Any = field(default=None, repr=False)

    @classmethod
    def from_api(cls, data: Any, *, serial_number: str) -> TerminalPairing:
        """Build an instance from a Payrexx API payload."""
        # Reaching this point at all means HTTP 200, i.e. the terminal is known to
        # the account; an unpaired or unknown serial answers 404 instead.
        payload = data[0] if isinstance(data, list) and data else data
        if not isinstance(payload, dict):
            payload = {}
        return cls(
            serial_number=serial_number,
            paired=True,
            status=payload.get("status"),
            cashier_name=payload.get("cashierName") or payload.get("cashier_name"),
            configuration=payload.get("configuration") or {},
            raw=data,
        )

    # Configuration keys seen in the PHP SDK's ECR example. Exposed as properties
    # because a till needs them to render correctly — and because reading them off
    # the device beats hard-coding a per-client assumption.

    @property
    def currency(self) -> str | None:
        """Currency the terminal is configured for."""
        value = self.configuration.get("currency")
        return str(value) if value is not None else None

    @property
    def language(self) -> str | None:
        """Language the terminal displays."""
        value = self.configuration.get("language")
        return str(value) if value is not None else None

    @property
    def point_of_sale_name(self) -> str | None:
        """Merchant-facing name of this point of sale."""
        value = self.configuration.get("pointOfSaleName")
        return str(value) if value is not None else None

    @property
    def timezone(self) -> str | None:
        """Timezone the terminal stamps its transactions with."""
        value = self.configuration.get("timezone")
        return str(value) if value is not None else None

    @property
    def has_tipping(self) -> bool:
        """Whether the terminal is set up to prompt for a tip.

        Worth checking before sending ``tip_amount``: a terminal with tipping off
        may reject or silently drop it.
        """
        return bool(self.configuration.get("hasTipping"))


@dataclass(frozen=True)
class Subscription:
    """A recurring payment agreement.

    Field names follow the PHP SDK's response model. ``status`` is a bare string
    there too — see :class:`payrexx.enums.SubscriptionStatus` for the values
    observed so far.
    """

    id: int | None
    status: str | None
    amount: int | None = None
    currency: str | None = None
    payment_interval: str | None = None
    start: str | None = None
    end: str | None = None
    valid_until: str | None = None
    next_pay_date: str | None = None
    cancelled_date: str | None = None
    first_cancel_date: str | None = None
    psp_subscription_id: str | None = None
    reference_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Subscription:
        """Build an instance from a Payrexx API payload."""
        invoice = data.get("invoice") or {}
        return cls(
            id=_as_int(data.get("id")),
            status=data.get("status"),
            amount=_as_int(data.get("amount")),
            currency=data.get("currency") or invoice.get("currency"),
            payment_interval=data.get("paymentInterval"),
            start=data.get("start"),
            end=data.get("end"),
            valid_until=data.get("valid_until") or data.get("validUntil"),
            next_pay_date=data.get("nextPayDate") or data.get("next_pay_date"),
            cancelled_date=data.get("cancelledDate") or data.get("cancelled_date"),
            first_cancel_date=data.get("firstCancelDate") or data.get("first_cancel_date"),
            psp_subscription_id=data.get("pspSubscriptionId"),
            reference_id=data.get("referenceId"),
            raw=data,
        )

    @property
    def is_active(self) -> bool:
        """Is active."""
        return self.status == "active"


@dataclass(frozen=True)
class Invoice:
    """A reusable payment link ("Invoice" in Payrexx terms, ``/Invoice/``).

    Not an accounting document — that is :class:`Bill`. This is a hosted link that
    can be paid repeatedly unless it carries an expiry.
    """

    id: int | None
    hash: str | None
    link: str | None
    status: str | None
    created_at: datetime | None = None
    invoices: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Invoice:
        """Build an instance from a Payrexx API payload."""
        created = _as_int(data.get("createdAt"))
        return cls(
            id=_as_int(data.get("id")),
            hash=data.get("hash"),
            link=data.get("link"),
            status=data.get("status"),
            created_at=(datetime.fromtimestamp(created, tz=timezone.utc) if created else None),
            invoices=tuple(data.get("invoices") or ()),
            raw=data,
        )


@dataclass(frozen=True)
class Page:
    """A mini shop page hosted by Payrexx."""

    id: int | None
    link: str | None = None
    created_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Page:
        """Build an instance from a Payrexx API payload."""
        created = _as_int(data.get("createdAt"))
        return cls(
            id=_as_int(data.get("id")),
            link=data.get("link"),
            created_at=(datetime.fromtimestamp(created, tz=timezone.utc) if created else None),
            raw=data,
        )


@dataclass(frozen=True)
class Bill:
    """A QR-invoice / purchase-on-invoice document (``/Bill/``)."""

    id: int | None
    uuid: str | None = None
    number: str | None = None
    status: str | None = None
    payment_status: str | None = None
    payment_link: str | None = None
    total: int | None = None
    currency: str | None = None
    transactions: tuple[dict[str, Any], ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Bill:
        """Build an instance from a Payrexx API payload."""
        return cls(
            id=_as_int(data.get("id")),
            uuid=data.get("uuid"),
            number=data.get("number"),
            status=data.get("status"),
            payment_status=data.get("paymentStatus") or data.get("payment_status"),
            payment_link=data.get("paymentLink") or data.get("payment_link"),
            total=_as_int(data.get("total")),
            currency=data.get("currency"),
            transactions=tuple(data.get("transactions") or ()),
            meta=data.get("meta") or {},
            raw=data,
        )


@dataclass(frozen=True)
class Payout:
    """A payout of collected funds to the merchant's bank account."""

    id: int | None
    uuid: str | None = None
    status: str | None = None
    amount: int | None = None
    currency: str | None = None
    date: str | None = None
    total_fees: int | None = None
    is_manual_payout: bool = False
    destination: dict[str, Any] = field(default_factory=dict)
    merchant: dict[str, Any] = field(default_factory=dict)
    payer: dict[str, Any] = field(default_factory=dict)
    statement: dict[str, Any] = field(default_factory=dict)
    transfers: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Payout:
        """Build an instance from a Payrexx API payload."""
        return cls(
            id=_as_int(data.get("id")),
            uuid=data.get("uuid"),
            status=data.get("status"),
            amount=_as_int(data.get("amount")),
            currency=data.get("currency"),
            date=data.get("date"),
            total_fees=_as_int(data.get("totalFees")),
            is_manual_payout=bool(data.get("isManualPayout")),
            destination=data.get("destination") or {},
            merchant=data.get("merchant") or {},
            payer=data.get("payer") or {},
            statement=data.get("statement") or {},
            transfers=tuple(data.get("transfers") or ()),
            raw=data,
        )


@dataclass(frozen=True)
class QrCode:
    """A static QR code pointing at a webshop, rendered as SVG and PNG."""

    id: int | None
    qr_code: str | None = None
    svg: str | None = None
    png: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> QrCode:
        """Build an instance from a Payrexx API payload."""
        return cls(
            id=_as_int(data.get("id")),
            qr_code=data.get("qrCode") or data.get("qr_code"),
            svg=data.get("svg"),
            png=data.get("png"),
            raw=data,
        )


@dataclass(frozen=True)
class Design:
    """A look-and-feel profile, referenced by ``look_and_feel_profile``."""

    id: int | None
    name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Design:
        """Build an instance from a Payrexx API payload."""
        return cls(id=_as_int(data.get("id")), name=data.get("name"), raw=data)


@dataclass(frozen=True)
class PaymentMethodInfo:
    """Display metadata for one payment method.

    Observed shape from a live account::

        {
            "id": "mastercard",
            "name": "Mastercard",
            "label": {"en": "Mastercard"},
            "logo": {"en": "https://media.payrexx.com/.../card_mastercard.svg"},
            "options_by_psp": {
                "44": {"mode": "prod", "payment_types": [...], "currencies": ["CHF"]}
            },
        }

    Warning:
        **``id`` is the identifier, not ``name``.** ``id`` holds the lowercase code
        (``"mastercard"``) that the ``pm`` filter and
        :class:`payrexx.enums.PaymentMethod` expect; ``name`` is a human label
        (``"Mastercard"``). Passing ``name`` into a ``pm`` filter yields a filter
        Payrexx silently ignores.
    """

    id: str | None
    name: str | None = None
    label: dict[str, str] = field(default_factory=dict)
    logo: dict[str, str] = field(default_factory=dict)
    options_by_psp: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PaymentMethodInfo:
        """Build an instance from a Payrexx API payload."""

        def _as_lang_map(value: Any) -> dict[str, str]:
            # Both label and logo are per-language maps, but tolerate a bare string
            # in case Payrexx ever flattens them.
            if isinstance(value, dict):
                return {str(k): str(v) for k, v in value.items()}
            if isinstance(value, str):
                return {"en": value}
            return {}

        return cls(
            id=data.get("id"),
            name=data.get("name"),
            label=_as_lang_map(data.get("label")),
            logo=_as_lang_map(data.get("logo")),
            options_by_psp=data.get("options_by_psp") or data.get("optionsByPsp") or {},
            raw=data,
        )

    def label_for(self, language: str = "en", *, default: str | None = None) -> str | None:
        """Return the label in ``language``, falling back to English then ``name``."""
        return self.label.get(language) or self.label.get("en") or default or self.name

    def logo_for(self, language: str = "en") -> str | None:
        """Return the logo URL for ``language``, falling back to English."""
        return self.logo.get(language) or self.logo.get("en")

    def currencies(self, psp_id: int | str) -> tuple[str, ...]:
        """Currencies this method accepts on a given PSP.

        Worth checking before creating a gateway: a method enabled on the account
        may still not cover the currency you are charging in.
        """
        options = self.options_by_psp.get(str(psp_id)) or {}
        return tuple(options.get("currencies") or ())

    def payment_types(self, psp_id: int | str) -> tuple[str, ...]:
        """Payment types supported on a PSP, e.g. ``one-time``, ``subscription``.

        Use it to check that a method can do what you are about to ask — offering a
        subscription through a method that only does ``one-time`` fails at checkout,
        not at creation.
        """
        options = self.options_by_psp.get(str(psp_id)) or {}
        return tuple(options.get("payment_types") or ())


@dataclass(frozen=True)
class AuthToken:
    """A short-lived token granting a user access to the Payrexx back office."""

    auth_token: str | None
    link: str | None = None
    expires_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> AuthToken:
        """Build an instance from a Payrexx API payload."""
        return cls(
            auth_token=data.get("authToken") or data.get("auth_token"),
            link=data.get("link"),
            expires_at=(
                data.get("authTokenExpirationDate") or data.get("auth_token_expiration_date")
            ),
            raw=data,
        )
