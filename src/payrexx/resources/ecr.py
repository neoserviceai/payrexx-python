"""The ECR resource: driving a physical POS terminal.

Payrexx presents this as one interface across hardware vendors — you integrate
once and they translate to each terminal's own protocol. In practice only the
**NexGo N5, N6 and N86** are supported today.

.. warning::
   **No idempotency, and no sandbox.** Payrexx documents no idempotency header on
   ``POST /payment``, and a live test confirmed the gateway endpoint happily
   creates duplicates for identical requests. On a terminal a duplicate is a
   *second charge*. This module therefore never retries a payment request, and
   :meth:`EcrResource.create_payment` exposes ``client_reference`` so callers can
   recover state by reading back rather than by resending. There is also no
   documented ECR simulator, so nothing here is exercisable without hardware.
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
    ) -> Any:
        """Pair a terminal with the account.

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
        return self._call("POST", self._path(serial_number, "pair"), data=payload)

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
        shop_items: Iterable[Mapping[str, Any]] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> EcrPayment:
        """Send a payment request to a paired terminal.

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
            shop_items: Line items; each needs at least ``name``.

        Returns:
            An :class:`~payrexx.models.EcrPayment` whose ``payment_id`` must be
            persisted immediately — it is what :meth:`get_payment`,
            :meth:`cancel_payment` and :meth:`void_payment` address.

        Warning:
            **Never retry this call blindly.** It is not idempotent: a request that
            times out may well have reached the terminal, and resending it can
            charge the customer twice. On a
            :class:`~payrexx.errors.PayrexxTransportError`, treat the outcome as
            unknown and reconcile — poll :meth:`get_payment` with the id if you got
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
            values, so :attr:`EcrPayment.status` is returned as a raw string. For
            state you can rely on, use the transaction webhook
            (``type == "POS-Terminal"``), whose statuses are documented.
        """
        suffix = f"payment/{self._client.quote_segment(payment_id)}"
        data = self._call("GET", self._path(serial_number, suffix))
        return EcrPayment.from_api(_unwrap(data), serial_number=serial_number)

    def cancel_payment(self, serial_number: str, payment_id: str) -> Any:
        """Cancel a payment still in progress on the terminal."""
        return self._call(
            "POST",
            self._path(serial_number, "payment/cancel"),
            data={"paymentId": payment_id},
        )

    def void_payment(self, serial_number: str, payment_id: str) -> Any:
        """Void a completed payment, before settlement.

        A void is all-or-nothing and generally only possible on the same day. For a
        partial return, or once settled, a refund is needed instead — and refunds
        are **not available over ECR on NexGo devices**, so that path goes through
        the merchant API.
        """
        return self._call(
            "POST",
            self._path(serial_number, "payment/void"),
            data={"paymentId": payment_id},
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def payment_methods(self, serial_number: str) -> Any:
        """Ask the terminal which payment methods it accepts."""
        return self._call("POST", self._path(serial_number, "paymentMethods"))


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}
