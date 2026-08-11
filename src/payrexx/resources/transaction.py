"""The Transaction resource: reading and refunding transactions."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from payrexx.models import Transaction

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


class TransactionResource:
    """``/Transaction/`` endpoints."""

    def __init__(self, client: PayrexxClient) -> None:
        self._client = client

    def list(self, *, offset: int | None = None, limit: int | None = None) -> list[Transaction]:
        """List the account's transactions."""
        params: dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        data = self._client.get("Transaction/", params=params or None)
        rows = data if isinstance(data, list) else [data] if data else []
        return [Transaction.from_api(row) for row in rows]

    def retrieve(self, transaction_id: int | str) -> Transaction:
        """Read one transaction."""
        data = self._client.get(
            f"Transaction/{self._client.quote_segment(transaction_id)}/"
        )
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
            f"Transaction/{self._client.quote_segment(transaction_id)}/refund/",
            data=payload or None,
        )
        return Transaction.from_api(_unwrap(data))

    def capture(self, transaction_id: int | str, *, amount: int | None = None) -> Transaction:
        """Capture a pre-authorised or reserved transaction."""
        payload: dict[str, Any] = {}
        if amount is not None:
            payload["amount"] = amount
        data = self._client.post(
            f"Transaction/{self._client.quote_segment(transaction_id)}/capture/",
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
