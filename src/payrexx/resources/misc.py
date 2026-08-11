"""The remaining Payrexx resources, each small enough not to warrant its own module.

Covers ``/Invoice/``, ``/Page/``, ``/Bill/``, ``/Payout/``, ``/QrCode/``,
``/QrCodeScan/``, ``/Design/``, ``/PaymentMethod/``, ``/SignatureCheck/`` and
``/AuthToken/``. Shapes and field names come from the official PHP SDK's request
and response models, which document more than the REST reference does.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from payrexx.models import (
    AuthToken,
    Bill,
    Design,
    Invoice,
    Page,
    PaymentMethodInfo,
    Payout,
    QrCode,
)

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, builtins.list):
        return data[0] if data else {}
    return data or {}


def _rows(data: Any) -> builtins.list[dict[str, Any]]:
    if isinstance(data, builtins.list):
        return data
    return [data] if data else []


class _Resource:
    def __init__(self, client: PayrexxClient) -> None:
        self._client = client


class InvoiceResource(_Resource):
    """``/Invoice/`` — a reusable hosted payment link.

    Not an accounting document; that is :class:`BillResource`. Payrexx's naming is
    confusing here, and the two live at different endpoints.
    """

    def create(
        self,
        *,
        title: str,
        description: str,
        amount: int,
        currency: str,
        reference_id: str | None = None,
        purpose: str | None = None,
        name: str | None = None,
        vat_rate: float | None = None,
        sku: str | None = None,
        expiration_date: str | None = None,
        button_text: str | None = None,
        payment_methods: Iterable[str] | None = None,
        psp: Iterable[int] | None = None,
        pre_authorization: bool | None = None,
        reservation: bool | None = None,
        success_redirect_url: str | None = None,
        failed_redirect_url: str | None = None,
        fields: Mapping[str, Any] | None = None,
        subscription_state: bool | None = None,
        subscription_interval: str | None = None,
        subscription_period: str | None = None,
        subscription_cancellation_interval: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Invoice:
        """Create a payment link.

        Args:
            expiration_date: After this date the link stops accepting payments.
        """
        payload: dict[str, Any] = {
            "title": title,
            "description": description,
            "amount": amount,
            "currency": currency,
            "referenceId": reference_id,
            "purpose": purpose,
            "name": name,
            "vatRate": vat_rate,
            "sku": sku,
            "expirationDate": expiration_date,
            "buttonText": button_text,
            "preAuthorization": pre_authorization,
            "reservation": reservation,
            "successRedirectUrl": success_redirect_url,
            "failedRedirectUrl": failed_redirect_url,
            "fields": dict(fields) if fields else None,
            "subscriptionState": subscription_state,
            "subscriptionInterval": subscription_interval,
            "subscriptionPeriod": subscription_period,
            "subscriptionCancellationInterval": subscription_cancellation_interval,
        }
        if payment_methods is not None:
            payload["pm"] = [str(m) for m in payment_methods]
        if psp is not None:
            payload["psp"] = builtins.list(psp)
        if extra:
            payload.update(extra)
        return Invoice.from_api(_unwrap(self._client.post("Invoice/", data=payload)))

    def retrieve(self, invoice_id: int | str) -> Invoice:
        """Read one record by id."""
        path = f"Invoice/{self._client.quote_segment(invoice_id)}/"
        return Invoice.from_api(_unwrap(self._client.get(path)))

    def delete(self, invoice_id: int | str) -> None:
        """Delete the record. Irreversible."""
        self._client.delete(f"Invoice/{self._client.quote_segment(invoice_id)}/")


class PageResource(_Resource):
    """``/Page/`` — a hosted mini shop."""

    def list(self) -> builtins.list[Page]:
        """List the records on this account."""
        return [Page.from_api(r) for r in _rows(self._client.get("Page/"))]

    def retrieve(self, page_id: int | str) -> Page:
        """Read one record by id."""
        path = f"Page/{self._client.quote_segment(page_id)}/"
        return Page.from_api(_unwrap(self._client.get(path)))

    def create(
        self,
        *,
        title: str,
        description: str,
        amount: int,
        currency: str,
        name: str | None = None,
        purpose: str | None = None,
        psp: Iterable[int] | None = None,
        pre_authorization: bool | None = None,
        reservation: bool | None = None,
        fields: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Page:
        """Create a record."""
        payload: dict[str, Any] = {
            "title": title,
            "description": description,
            "amount": amount,
            "currency": currency,
            "name": name,
            "purpose": purpose,
            "preAuthorization": pre_authorization,
            "reservation": reservation,
            "fields": dict(fields) if fields else None,
        }
        if psp is not None:
            payload["psp"] = builtins.list(psp)
        if extra:
            payload.update(extra)
        return Page.from_api(_unwrap(self._client.post("Page/", data=payload)))


class BillResource(_Resource):
    """``/Bill/`` — QR invoices and purchase-on-invoice documents.

    This is the accounting-flavoured one: positions, due dates, reminders,
    attachments. The Swiss QR-bill flow lives here.
    """

    def list(self, *, offset: int | None = None, limit: int | None = None) -> builtins.list[Bill]:
        """List the records on this account."""
        params: dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        data = self._client.get("Bill/", params=params or None)
        return [Bill.from_api(r) for r in _rows(data)]

    def retrieve(self, bill_id: int | str) -> Bill:
        """Read one record by id."""
        path = f"Bill/{self._client.quote_segment(bill_id)}/"
        return Bill.from_api(_unwrap(self._client.get(path)))

    def create(
        self,
        *,
        currency: str,
        positions: Iterable[Mapping[str, Any]],
        recipient: Mapping[str, Any] | None = None,
        reference: str | None = None,
        date: str | None = None,
        due_after_days: int | None = None,
        note: str | None = None,
        terms: str | None = None,
        language: str | None = None,
        send: bool | None = None,
        complete: bool | None = None,
        shipping_cost: int | None = None,
        discount: Mapping[str, Any] | None = None,
        cash_discounts: Iterable[Mapping[str, Any]] | None = None,
        reminders: Iterable[Mapping[str, Any]] | None = None,
        additional_recipients: Iterable[str] | None = None,
        attachments: Iterable[Mapping[str, Any]] | None = None,
        bank_information: Mapping[str, Any] | None = None,
        service_period: Mapping[str, Any] | None = None,
        payout_descriptor: str | None = None,
        payment_methods: Iterable[str] | None = None,
        psp: Iterable[int] | None = None,
        design: int | str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Bill:
        """Create a bill.

        Args:
            positions: Line items — required.
            send: Whether Payrexx emails the bill to the recipient. Leave unset (or
                ``False``) while testing, so a draft does not reach a real customer.
            complete: Whether to finalise the bill rather than keep it a draft.
        """
        payload: dict[str, Any] = {
            "currency": currency,
            "positions": [dict(p) for p in positions],
            "recipient": dict(recipient) if recipient else None,
            "reference": reference,
            "date": date,
            "dueAfterDays": due_after_days,
            "note": note,
            "terms": terms,
            "language": language,
            "send": send,
            "complete": complete,
            "shippingCost": shipping_cost,
            "discount": dict(discount) if discount else None,
            "bankInformation": dict(bank_information) if bank_information else None,
            "servicePeriod": dict(service_period) if service_period else None,
            "payoutDescriptor": payout_descriptor,
            "design": design,
        }
        if cash_discounts is not None:
            payload["cashDiscounts"] = [dict(d) for d in cash_discounts]
        if reminders is not None:
            payload["reminders"] = [dict(r) for r in reminders]
        if additional_recipients is not None:
            payload["additionalRecipients"] = builtins.list(additional_recipients)
        if attachments is not None:
            payload["attachments"] = [dict(a) for a in attachments]
        if payment_methods is not None:
            payload["pm"] = [str(m) for m in payment_methods]
        if psp is not None:
            payload["psp"] = builtins.list(psp)
        if extra:
            payload.update(extra)
        return Bill.from_api(_unwrap(self._client.post("Bill/", data=payload)))

    def update(self, bill_id: int | str, **fields: Any) -> Bill:
        """Update a bill. Sent as ``PUT``."""
        path = f"Bill/{self._client.quote_segment(bill_id)}/"
        return Bill.from_api(_unwrap(self._client.put(path, data=fields)))

    def patch(self, bill_id: int | str, **fields: Any) -> Bill:
        """Partially update a bill. Sent as ``PATCH``."""
        path = f"Bill/{self._client.quote_segment(bill_id)}/"
        return Bill.from_api(_unwrap(self._client.patch(path, data=fields)))

    def delete(self, bill_id: int | str) -> None:
        """Delete the record. Irreversible."""
        self._client.delete(f"Bill/{self._client.quote_segment(bill_id)}/")


class PayoutResource(_Resource):
    """``/Payout/`` — transfers of collected funds to the merchant."""

    def list(self, *, offset: int | None = None, limit: int | None = None) -> builtins.list[Payout]:
        """List the records on this account."""
        params: dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        data = self._client.get("Payout/", params=params or None)
        return [Payout.from_api(r) for r in _rows(data)]

    def retrieve(self, payout_uuid: str) -> Payout:
        """Read one record by id."""
        path = f"Payout/{self._client.quote_segment(payout_uuid)}/"
        return Payout.from_api(_unwrap(self._client.get(path)))

    def details(self, payout_uuid: str) -> Payout:
        """Read a payout with its individual transfers.

        Note:
            **v1.16 changed this endpoint.** It now resolves payout aggregates into
            the underlying transfers; before, a repeated payout attempt came back as
            a single aggregate row with an empty transaction object. This client
            pins v1.16, so the resolved form is what you get.
        """
        path = f"Payout/{self._client.quote_segment(payout_uuid)}/details"
        return Payout.from_api(_unwrap(self._client.get(path)))


class QrCodeResource(_Resource):
    """``/QrCode/`` — static QR codes pointing at a webshop.

    A shopper scans the code, which opens a session; pass that session id to
    :meth:`payrexx.resources.gateway.GatewayResource.create` as
    ``qr_code_session_id`` to bind the payment to the scan.
    """

    def create(self, *, webshop_url: str) -> QrCode:
        """Create a record."""
        data = self._client.post("QrCode/", data={"webshopUrl": webshop_url})
        return QrCode.from_api(_unwrap(data))

    def retrieve(self, qr_code_id: int | str) -> QrCode:
        """Read one record by id."""
        path = f"QrCode/{self._client.quote_segment(qr_code_id)}/"
        return QrCode.from_api(_unwrap(self._client.get(path)))

    def delete(self, qr_code_id: int | str) -> None:
        """Delete the record. Irreversible."""
        self._client.delete(f"QrCode/{self._client.quote_segment(qr_code_id)}/")

    def delete_scan(self, session_id: str) -> None:
        """End a scan session (``DELETE /QrCodeScan/``)."""
        self._client.delete(
            f"QrCodeScan/{self._client.quote_segment(session_id)}/",
            data={"sessionId": session_id},
        )


class DesignResource(_Resource):
    """``/Design/`` — look-and-feel profiles for hosted pages.

    Pass a design's id to a gateway as ``look_and_feel_profile``.
    """

    def list(self) -> builtins.list[Design]:
        """List the records on this account."""
        return [Design.from_api(r) for r in _rows(self._client.get("Design/"))]

    def retrieve(self, design_id: int | str) -> Design:
        """Read one record by id."""
        path = f"Design/{self._client.quote_segment(design_id)}/"
        return Design.from_api(_unwrap(self._client.get(path)))

    def create(self, *, name: str, **style: Any) -> Design:
        """Create a design.

        Args:
            style: Any of the ~30 style keys the PHP SDK exposes —
                ``backgroundColor``, ``buttonColor``, ``fontFamily``, ``fontSize``,
                ``headerImage``, ``linkColor``, ``textColor``,
                ``enableRoundedCorners``, the ``VPOS*`` variants, and so on. Passed
                through as given.
        """
        return Design.from_api(_unwrap(self._client.post("Design/", data={"name": name, **style})))

    def update(self, design_id: int | str, **style: Any) -> Design:
        """Update a design.

        Note:
            Sent as ``POST``, not ``PUT``. The PHP SDK special-cases exactly this:
            ``update`` maps to ``PUT`` for every model *except* ``Design``.
        """
        path = f"Design/{self._client.quote_segment(design_id)}/"
        return Design.from_api(_unwrap(self._client.post(path, data=style)))

    def delete(self, design_id: int | str) -> None:
        """Delete the record. Irreversible."""
        self._client.delete(f"Design/{self._client.quote_segment(design_id)}/")


class PaymentMethodResource(_Resource):
    """``/PaymentMethod/`` — display metadata (labels, logos) per method."""

    def list(
        self,
        *,
        currency: str | None = None,
        payment_type: str | None = None,
        psp: int | str | None = None,
    ) -> builtins.list[PaymentMethodInfo]:
        """List payment methods, optionally filtered.

        Use this for rendering a chooser. To know what the account can actually
        accept, use
        :meth:`payrexx.resources.payment_provider.PaymentProviderResource.active_payment_methods`
        instead — this endpoint describes methods, it does not tell you which are
        enabled.
        """
        params: dict[str, Any] = {}
        if currency is not None:
            params["filterCurrency"] = currency
        if payment_type is not None:
            params["filterPaymentType"] = payment_type
        if psp is not None:
            params["filterPsp"] = psp
        data = self._client.get("PaymentMethod/", params=params or None)
        return [PaymentMethodInfo.from_api(r) for r in _rows(data)]

    def retrieve(self, name: str) -> PaymentMethodInfo:
        """Read one record by id."""
        path = f"PaymentMethod/{self._client.quote_segment(name)}/"
        return PaymentMethodInfo.from_api(_unwrap(self._client.get(path)))


class SignatureCheckResource(_Resource):
    """``/SignatureCheck/`` — validates instance name and API secret.

    The cheapest possible credential probe: no parameters, no side effects.
    """

    def check(self) -> bool:
        """Return whether the credentials are accepted.

        Never raises on a rejection — an authentication failure returns ``False``.
        Transport failures still propagate, since they say nothing about the keys.
        """
        from payrexx.errors import AuthenticationError, PayrexxError, PayrexxTransportError

        try:
            self._client.get("SignatureCheck/")
        except PayrexxTransportError:
            raise
        except (AuthenticationError, PayrexxError):
            return False
        return True


class AuthTokenResource(_Resource):
    """``/AuthToken/`` — short-lived back-office access for a given user."""

    def create(self, *, user_id: int | str) -> AuthToken:
        """Mint a token, and the link that consumes it.

        Warning:
            The returned link grants access to the Payrexx back office as that user.
            Treat it as a credential: hand it straight to the intended person over a
            channel you trust, and never log it.
        """
        data = self._client.post("AuthToken/", data={"userId": user_id})
        return AuthToken.from_api(_unwrap(data))
