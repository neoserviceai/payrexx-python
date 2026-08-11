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
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Gateway:
        created = _as_int(data.get("createdAt"))
        return cls(
            id=_as_int(data.get("id")),
            hash=data.get("hash") or "",
            link=data.get("link") or "",
            status=TransactionStatus.parse(data.get("status")),
            reference_id=data.get("referenceId"),
            amount=_as_int(data.get("amount")),
            currency=data.get("currency"),
            created_at=(
                datetime.fromtimestamp(created, tz=timezone.utc) if created else None
            ),
            invoices=tuple(data.get("invoices") or ()),
            payment_methods=tuple(data.get("pm") or ()),
            psp=tuple(data.get("psp") or ()),
            raw=data,
        )

    @property
    def is_paid(self) -> bool:
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
    def from_api(
        cls, data: dict[str, Any], *, serial_number: str | None = None
    ) -> EcrPayment:
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
    """Pairing state of a POS terminal."""

    serial_number: str
    paired: bool
    raw: Any = field(default=None, repr=False)

    @classmethod
    def from_api(cls, data: Any, *, serial_number: str) -> TerminalPairing:
        # Payrexx returns a loosely-typed payload here (the reference shows a list
        # of strings). Reaching this point at all means HTTP 200, i.e. the terminal
        # is known to the account; an unpaired serial answers 404 instead.
        return cls(serial_number=serial_number, paired=True, raw=data)
