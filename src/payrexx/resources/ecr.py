"""The ECR resource: driving a physical POS terminal.

Payrexx presents this as one interface across hardware vendors — you integrate
once and they translate to each terminal's own protocol. In practice only the
**NexGo N5, N6 and N86** are supported today.

!!! warning "No idempotency, and no sandbox"
    Payrexx documents no idempotency header on ``POST /payment``, and a live test
    confirmed the gateway endpoint happily creates duplicates for identical
    requests. On a terminal a duplicate is a *second charge*, so this module never
    retries a payment request — a transport failure raises
    ``PayrexxTransportError`` and the caller reconciles by reading back rather than
    resending. There is also no documented ECR simulator, so nothing here is
    exercisable without hardware.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from payrexx.client import ECR_API_VERSION
from payrexx.models import EcrPayment, TerminalPairing

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


class EcrResource:
    """``/ecr/{serialNumber}/*`` endpoints."""

    def __init__(self, client: PayrexxClient) -> None:
        self._client = client

    def _call(self, method: str, suffix: str, **kwargs: Any) -> Any:
        return self._client.request(
            method,
            suffix,
            api_version=ECR_API_VERSION,
            use_pos_secret=True,
            **kwargs,
        )

    def _path(self, serial_number: str, suffix: str = "") -> str:
        serial = self._client.quote_segment(serial_number)
        return f"ecr/{serial}/{suffix.lstrip('/')}" if suffix else f"ecr/{serial}"

    # ------------------------------------------------------------------
    # Pairing
    # ------------------------------------------------------------------

    def get_pairing(self, serial_number: str) -> TerminalPairing:
        """Read a terminal's pairing state.

        Raises:
            TerminalNotFoundError: The serial is unknown *or* not paired with this
                account — Payrexx answers ``404 Terminal not found`` for both, so a
                404 does not prove the serial is wrong.
        """
        data = self._call("GET", self._path(serial_number, "pair"))
        return TerminalPairing.from_api(data, serial_number=serial_number)

    def pair(
        self,
        serial_number: str,
        pairing_code: str,
        *,
        cashier_name: str | None = None,
    ) -> TerminalPairing:
        """Pair a terminal with the account.

        Returns the same :class:`~payrexx.models.TerminalPairing` as
        :meth:`get_pairing`, so a caller can read the currency, language and tipping
        settings straight off the result. It used to hand back the raw dict, which
        made ``pairing.currency`` an ``AttributeError`` on the one call where you
        most want it — the moment a terminal is first connected.

        A successful pairing reports ``pairingStatus: AUTHORIZED``, not ``PAIRED``.

        Args:
            serial_number: Printed on the device and shown in the account.
            pairing_code: The six-character code from the terminal — open the
                hamburger menu (☰, top left) and choose *Connect to cash register*.
                It is **short-lived and is regenerated if you leave that screen**,
                so read it and call this immediately.
            cashier_name: Label for the device; defaults to the terminal name.
        """
        payload: dict[str, Any] = {"pairingCode": pairing_code}
        if cashier_name:
            payload["cashierName"] = cashier_name
        data = self._call("POST", self._path(serial_number, "pair"), data=payload)
        # Same shape as get_pairing, which does not unwrap either — the pairing
        # endpoints answer with the object directly, unlike the payment ones.
        return TerminalPairing.from_api(data, serial_number=serial_number)

    def unpair(self, serial_number: str) -> Any:
        """Release a terminal from the account."""
        return self._call("DELETE", self._path(serial_number, "pair"))

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------

    def create_payment(
        self,
        serial_number: str,
        *,
        amount: int,
        currency: str,
        payment_method: str | None = None,
        payment_reference: str | None = None,
        print_slip: bool | None = None,
        tip_amount: int | None = None,
        purpose: str | None = None,
        discount: Mapping[str, Any] | None = None,
        shop_items: Iterable[Mapping[str, Any]] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> EcrPayment:
        """Send a payment request to a paired terminal.

        Warning:
            **Not idempotent.** Payrexx confirmed on 2026-08-18 that this endpoint
            has no idempotency header or equivalent: two identical calls take two
            payments. Guard against double submission on your side — and never
            retry it on a timeout, because a request that timed out may well have
            reached the terminal. This is why POST is excluded from the client's
            retryable methods.

            The ``payment_reference`` you pass here comes back in the webhook as
            ``invoice.purpose``, **not** as ``referenceId``. That field exists on
            POS deliveries too but is not reserved for you — TWINT puts its own
            identifier in it — so match on
            :attr:`payrexx.models.Transaction.purpose`.

        Args:
            amount: Amount in the smallest currency unit — ``1500`` is CHF 15.00.
            currency: ISO 4217 code.
            payment_method: ``"card"`` or ``"twint"``. Omit to let the terminal show
                its own chooser.
            payment_reference: Your identifier for this payment. Pass it always —
                it is the only thread linking the terminal payment back to your
                order once the webhook arrives.
            print_slip: Whether the terminal prints a receipt.
            tip_amount: Added on top of ``amount``.
            purpose: Free-text description shown on the terminal and the receipt.
            discount: Discount object, as accepted by the PHP SDK.
            shop_items: Line items; build them with `shop_item`.

        Returns:
            An [`EcrPayment`][payrexx.models.EcrPayment] whose ``payment_id`` must be
            persisted immediately — it is what `get_payment`,
            `cancel_payment` and `void_payment` address.

        Warning:
            **Never retry this call blindly.** It is not idempotent: a request that
            times out may well have reached the terminal, and resending it can
            charge the customer twice. On a
            [`PayrexxTransportError`][payrexx.errors.PayrexxTransportError], treat the outcome as
            unknown and reconcile — poll `get_payment` with the id if you got
            one, otherwise wait for the transaction webhook and match on
            ``payment_reference``.
        """
        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "paymentMethod": payment_method,
            "paymentReference": payment_reference,
            "printSlip": print_slip,
            "tipAmount": tip_amount,
            "purpose": purpose,
            "discount": dict(discount) if discount else None,
        }
        if shop_items is not None:
            payload["shopItems"] = [dict(item) for item in shop_items]
        if extra:
            payload.update(extra)

        data = self._call("POST", self._path(serial_number, "payment"), data=payload)
        return EcrPayment.from_api(_unwrap(data), serial_number=serial_number)

    def get_payment(self, serial_number: str, payment_id: str) -> EcrPayment:
        """Read the state of a terminal payment.

        Note:
            Payrexx's OpenAPI does not enumerate the possible ``payment_status``
            values, so `EcrPayment.status` is returned as a raw string. For
            state you can rely on, use the transaction webhook
            (``type == "POS-Terminal"``), whose statuses are documented.
        """
        suffix = f"payment/{self._client.quote_segment(payment_id)}"
        data = self._call("GET", self._path(serial_number, suffix))
        return EcrPayment.from_api(_unwrap(data), serial_number=serial_number)

    def cancel_payment(self, serial_number: str, payment_id: str) -> EcrPayment:
        """Cancel a payment still in progress on the terminal.

        Note:
            The payment id goes **in the path**, not the body. The REST reference
            shows ``POST /ecr/{sn}/payment/cancel``, but the official PHP SDK builds
            ``POST /ecr/{sn}/payment/{id}/cancel`` (``setPaymentId()`` assigns
            ``'payment/' + id`` as the resource id, and ``cancel`` becomes the
            action segment). Both spellings return the same error against an
            unpaired terminal, so they could not be told apart without hardware —
            the SDK is followed here as the more authoritative source.
        """
        suffix = f"payment/{self._client.quote_segment(payment_id)}/cancel"
        data = self._call("POST", self._path(serial_number, suffix))
        return EcrPayment.from_api(_unwrap(data), serial_number=serial_number)

    def void_payment(self, serial_number: str, payment_id: str) -> EcrPayment:
        """Void a completed payment, before settlement — all or nothing.

        Payrexx guarantees a **three-month** window (confirmed 2026-08-18), not the
        same day as previously assumed, with one exception you cannot detect from
        the API: on TWINT it only holds while the customer still has the same app
        and phone. So prefer *attempting* the void and falling back to a refund over
        predicting whether it will be accepted.

        For a partial return, a refund is needed instead — and
        `POST /ecr/{sn}/payment/{id}/refund` answers **501 Not Implemented on
        NexGo**, so that path goes through
        [`payrexx.resources.transaction.TransactionResource.refund`][payrexx.resources.transaction.TransactionResource.refund].
        On Newland terminals a refund goes through this same reversal mechanism.

        The id is in the path, for the same reason as `cancel_payment`.
        """
        suffix = f"payment/{self._client.quote_segment(payment_id)}/void"
        data = self._call("POST", self._path(serial_number, suffix))
        return EcrPayment.from_api(_unwrap(data), serial_number=serial_number)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def payment_methods(self, serial_number: str) -> Any:
        """Ask the terminal which payment methods it accepts.

        Note:
            Sent as ``GET``. The REST reference documents ``POST``, but the PHP SDK
            maps ``getEcrPaymentMethods`` to ``GET``; both are accepted by the
            router. Following the SDK.
        """
        return self._call("GET", self._path(serial_number, "paymentMethods"))

    @staticmethod
    def shop_item(
        name: str,
        price: int,
        *,
        quantity: str | int = 1,
        unit: str | None = "pc",
        vat: int | None = None,
        discount: int | None = 0,
    ) -> dict[str, Any]:
        """Build one ``shopItems`` entry, mirroring the PHP SDK's ``addShopItem``.

        Args:
            name: Required by the API.
            price: In the smallest currency unit.
            quantity: The SDK types this as a string; either is accepted here and
                serialised the same way.
        """
        return {
            "name": name,
            "price": price,
            "quantity": quantity,
            "unit": unit,
            "vat": vat,
            "discount": discount,
        }


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}
