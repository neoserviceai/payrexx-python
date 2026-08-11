"""The Gateway resource: hosted payment pages.

This is the web-checkout path. Create a gateway, send the shopper to
:attr:`~payrexx.models.Gateway.link`, and let the transaction webhook confirm the
outcome.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from payrexx.models import Gateway

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


class GatewayResource:
    """``/Gateway/`` endpoints."""

    def __init__(self, client: PayrexxClient) -> None:
        self._client = client

    def create(
        self,
        *,
        amount: int,
        currency: str,
        reference_id: str | None = None,
        purpose: str | None = None,
        success_redirect_url: str | None = None,
        failed_redirect_url: str | None = None,
        cancel_redirect_url: str | None = None,
        payment_methods: Iterable[str] | None = None,
        psp: Iterable[int] | None = None,
        vat_rate: float | None = None,
        sku: str | None = None,
        language: str | None = None,
        pre_authorization: bool | None = None,
        reservation: bool | None = None,
        charge_on_authorization: bool | None = None,
        reserve_on_authorization: bool | None = None,
        fields: Mapping[str, Any] | None = None,
        basket: Iterable[Mapping[str, Any]] | None = None,
        button_text: str | None = None,
        success_message: str | None = None,
        skip_result_page: bool | None = None,
        is_price_exclusive_vat: bool | None = None,
        customer_statement_descriptor: str | None = None,
        look_and_feel_profile: str | None = None,
        validity: int | None = None,
        return_app: str | None = None,
        qr_code_session_id: str | None = None,
        subscription_state: bool | None = None,
        subscription_interval: str | None = None,
        subscription_period: str | None = None,
        subscription_cancellation_interval: str | None = None,
        subscription_period_min_amount: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Gateway:
        """Create a hosted payment page.

        Args:
            amount: Amount in the smallest currency unit — ``1500`` is CHF 15.00.
            currency: ISO 4217 code, e.g. ``"CHF"``.
            reference_id: Your own identifier. It travels back on the gateway and
                on the transaction webhook, which makes it the natural anchor to
                your order or invoice. **It does not enforce uniqueness** — see the
                warning below.
            payment_methods: Restrict the methods offered on the page. Encoded as
                ``pm[0]``, ``pm[1]``, … because that is the only form Payrexx
                honours; check :attr:`Gateway.filter_was_applied` if it matters.
            psp: Restrict to specific PSP ids (``44`` is Payrexx Pay).
            fields: Prefilled contact fields, nested as
                ``{"forename": {"value": "Jean"}}``.
            basket: Line items shown on the payment page.
            pre_authorization: Authorise now, charge later via
                :meth:`~payrexx.resources.transaction.TransactionResource.capture`.
            reservation: Reserve the amount for a manual charge.
            charge_on_authorization: Charge immediately on authorisation.
            skip_result_page: Send the shopper straight to the redirect URL instead
                of showing Payrexx's own confirmation page.
            is_price_exclusive_vat: Whether ``amount`` excludes VAT.
            customer_statement_descriptor: What the shopper sees on their statement.
            look_and_feel_profile: Id of a *Design* to style the page with; create
                one through :attr:`~payrexx.client.PayrexxClient.design`.
            validity: Lifetime of the link, in minutes.
            return_app: Deep link back into a mobile app after payment.
            qr_code_session_id: Ties this gateway to a static-QR scan session; see
                :attr:`~payrexx.client.PayrexxClient.qr_code`.
            subscription_state: Turn the payment into a recurring subscription.
            subscription_interval: Billing period as an ISO 8601 duration, e.g.
                ``"P1M"`` — see :class:`payrexx.enums.Interval`.
            subscription_period: Total duration of the subscription.
            subscription_cancellation_interval: Notice period for cancellation.
            subscription_period_min_amount: Minimum amount over the period.
            extra: Escape hatch for parameters this signature does not cover;
                merged last, so it can override anything above. The PHP SDK also
                accepts ``concardisOrderId``, ``spotlightStatus`` and
                ``spotlightOrderDetailsUrl``, which are integration-specific and
                intentionally left out of the signature.

        Returns:
            The created :class:`~payrexx.models.Gateway`, whose ``link`` is the URL
            to send the shopper to.

        Warning:
            **There is no idempotency.** Two identical calls with the same
            ``reference_id`` create two independent gateways — verified against a
            live account. Call this once per order and persist the returned ``id``
            and ``hash``; to recover after a crash, use :meth:`find_by_reference`
            instead of creating a second gateway.
        """
        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "referenceId": reference_id,
            "purpose": purpose,
            "successRedirectUrl": success_redirect_url,
            "failedRedirectUrl": failed_redirect_url,
            "cancelRedirectUrl": cancel_redirect_url,
            "vatRate": vat_rate,
            "sku": sku,
            "language": language,
            "preAuthorization": pre_authorization,
            "reservation": reservation,
            "chargeOnAuthorization": charge_on_authorization,
            "reserveOnAuthorization": reserve_on_authorization,
            "fields": dict(fields) if fields else None,
            "buttonText": button_text,
            "successMessage": success_message,
            "skipResultPage": skip_result_page,
            "isPriceExclusiveVat": is_price_exclusive_vat,
            "customerStatementDescriptor": customer_statement_descriptor,
            "lookAndFeelProfile": look_and_feel_profile,
            "validity": validity,
            "returnApp": return_app,
            "qrCodeSessionId": qr_code_session_id,
            "subscriptionState": subscription_state,
            "subscriptionInterval": subscription_interval,
            "subscriptionPeriod": subscription_period,
            "subscriptionCancellationInterval": subscription_cancellation_interval,
            "subscriptionPeriodMinAmount": subscription_period_min_amount,
        }
        if payment_methods is not None:
            payload["pm"] = [str(m) for m in payment_methods]
        if psp is not None:
            payload["psp"] = list(psp)
        if basket is not None:
            payload["basket"] = [dict(item) for item in basket]
        if extra:
            payload.update(extra)

        data = self._client.post("Gateway/", data=payload)
        return Gateway.from_api(_first(data))

    def retrieve(self, gateway_id: int | str) -> Gateway:
        """Read a gateway back, including its current status."""
        data = self._client.get(f"Gateway/{self._client.quote_segment(gateway_id)}/")
        return Gateway.from_api(_first(data))

    def delete(self, gateway_id: int | str) -> None:
        """Remove a gateway.

        Only meaningful while it is still unpaid; it does not reverse a payment.
        """
        self._client.delete(f"Gateway/{self._client.quote_segment(gateway_id)}/")

    def find_by_reference(self, reference_id: str) -> list[Gateway]:
        """Find gateways carrying ``reference_id``, newest first.

        Because ``reference_id`` is not unique, this can legitimately return more
        than one. Use it before creating a gateway when recovering from an
        interrupted flow, so a retry reuses the existing page instead of minting a
        duplicate.

        Note:
            Payrexx has no documented server-side filter for this, so the search
            runs over the transaction list. It therefore only finds gateways that
            already produced a transaction — a created-but-untouched gateway will
            not appear. Persisting the gateway id at creation time remains the
            reliable path; this is the fallback.
        """
        transactions = self._client.transaction.list()
        matches = [t for t in transactions if t.reference_id == reference_id]
        out: list[Gateway] = []
        for tx in matches:
            invoice = tx.raw.get("invoice") or {}
            link = invoice.get("paymentLink")
            out.append(
                Gateway(
                    id=tx.id,
                    hash=tx.uuid or "",
                    link=link or "",
                    status=tx.status,
                    reference_id=tx.reference_id,
                    amount=tx.amount,
                    currency=tx.currency,
                    created_at=None,
                    raw=tx.raw,
                )
            )
        return out


def _first(data: Any) -> dict[str, Any]:
    """Unwrap Payrexx's single-element ``data`` list."""
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}
