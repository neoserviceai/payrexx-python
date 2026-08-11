"""The Transaction resource: reading and refunding transactions."""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from payrexx.models import Transaction

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


class TransactionResource:
    """``/Transaction/`` endpoints."""

    def __init__(self, client: PayrexxClient) -> None:
        self._client = client

    def list(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        datetime_utc_greater_than: str | None = None,
        datetime_utc_less_than: str | None = None,
        my_transactions_only: bool | None = None,
        order_by_time: str | None = None,
    ) -> builtins.list[Transaction]:
        """List the account's transactions.

        Args:
            datetime_utc_greater_than: Lower bound on the transaction time (UTC).
            datetime_utc_less_than: Upper bound on the transaction time (UTC).
            my_transactions_only: Restrict to the calling user's own transactions.
            order_by_time: Sort direction on the time field.

        The filter names mirror the PHP SDK's ``filter*`` properties; none of them
        appear in the REST reference. Prefer filtering server-side over paging
        through everything — the rate limit is ~600 requests per 5 minutes.
        """
        params: dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        if datetime_utc_greater_than is not None:
            params["filterDatetimeUtcGreaterThan"] = datetime_utc_greater_than
        if datetime_utc_less_than is not None:
            params["filterDatetimeUtcLessThan"] = datetime_utc_less_than
        if my_transactions_only is not None:
            params["filterMyTransactionsOnly"] = 1 if my_transactions_only else 0
        if order_by_time is not None:
            params["orderByTime"] = order_by_time
        data = self._client.get("Transaction/", params=params or None)
        rows = data if isinstance(data, builtins.list) else [data] if data else []
        return [Transaction.from_api(row) for row in rows]

    def retrieve(self, transaction_id: int | str) -> Transaction:
        """Read one transaction."""
        data = self._client.get(f"Transaction/{self._client.quote_segment(transaction_id)}/")
        return Transaction.from_api(_unwrap(data))

    def refund(self, transaction_id: int | str, *, amount: int | None = None) -> Transaction:
        """Refund a transaction, fully or partially.

        Args:
            amount: Amount to refund in the smallest currency unit. ``None`` refunds
                the full remaining amount.

        Note:
            Check :attr:`Transaction.refundable` / ``partially_refundable`` first —
            they tell you what Payrexx will actually accept. This is also the path
            for returning a POS payment once it is settled, since NexGo terminals do
            not expose refunds over ECR.
        """
        payload: dict[str, Any] = {}
        if amount is not None:
            payload["amount"] = amount
        data = self._client.post(
            f"Transaction/{self._client.quote_segment(transaction_id)}/refund",
            data=payload or None,
        )
        return Transaction.from_api(_unwrap(data))

    def capture(self, transaction_id: int | str, *, amount: int | None = None) -> Transaction:
        """Capture a pre-authorised or reserved transaction."""
        payload: dict[str, Any] = {}
        if amount is not None:
            payload["amount"] = amount
        data = self._client.post(
            f"Transaction/{self._client.quote_segment(transaction_id)}/capture",
            data=payload or None,
        )
        return Transaction.from_api(_unwrap(data))

    def cancel(self, transaction_id: int | str) -> Transaction:
        """Cancel a transaction that has not been captured.

        Sent as ``DELETE``: the PHP SDK maps ``cancel`` to ``DELETE``, which is easy
        to get wrong since every other action verb on this resource is a ``POST``.
        """
        data = self._client.delete(f"Transaction/{self._client.quote_segment(transaction_id)}/")
        return Transaction.from_api(_unwrap(data))

    def charge(
        self,
        transaction_id: int | str,
        *,
        amount: int | None = None,
        currency: str | None = None,
        purpose: str | None = None,
        reference_id: str | None = None,
        vat_rate: float | None = None,
        fields: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Transaction:
        """Charge a stored payment means (a tokenisation).

        This is the merchant-initiated path: authorise once via a gateway with
        ``pre_authorization=True``, then charge the resulting transaction later
        without the shopper present.

        Warning:
            Not idempotent — calling it twice charges twice. Guard it on your side.
        """
        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "purpose": purpose,
            "referenceId": reference_id,
            "vatRate": vat_rate,
            "fields": dict(fields) if fields else None,
        }
        if extra:
            payload.update(extra)
        data = self._client.post(
            f"Transaction/{self._client.quote_segment(transaction_id)}/charge",
            data=payload,
        )
        return Transaction.from_api(_unwrap(data))

    def pre_authorize(
        self,
        transaction_id: int | str,
        *,
        amount: int | None = None,
        currency: str | None = None,
        purpose: str | None = None,
        reference_id: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Transaction:
        """Pre-authorise an amount against a stored payment means.

        Places a hold without capturing. Complete it with :meth:`capture`, or let it
        lapse — an authorisation that is never captured ends up ``uncaptured``.
        """
        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "purpose": purpose,
            "referenceId": reference_id,
        }
        if extra:
            payload.update(extra)
        data = self._client.post(
            f"Transaction/{self._client.quote_segment(transaction_id)}/preAuthorize",
            data=payload,
        )
        return Transaction.from_api(_unwrap(data))

    def send_receipt(
        self,
        transaction_id: int | str,
        *,
        recipient: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Transaction:
        """Email a receipt for a transaction.

        Args:
            recipient: Email address. When omitted, Payrexx uses the address held on
                the transaction's contact.

        Warning:
            This sends mail to a real person. Point it at your own address while
            testing.
        """
        payload: dict[str, Any] = {}
        if recipient is not None:
            payload["recipient"] = recipient
        if extra:
            payload.update(extra)
        data = self._client.post(
            f"Transaction/{self._client.quote_segment(transaction_id)}/receipt",
            data=payload or None,
        )
        return Transaction.from_api(_unwrap(data))

    def find_by_reference(self, reference_id: str) -> builtins.list[Transaction]:
        """Return every transaction carrying ``reference_id``.

        Payrexx does not enforce uniqueness on ``referenceId``, so this can return
        several rows — which is exactly why it is worth checking after a request
        whose outcome you are unsure of.
        """
        return [t for t in self.list() if t.reference_id == reference_id]


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return data[0] if data else {}
    return data or {}
