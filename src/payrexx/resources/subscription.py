"""The Subscription resource: recurring payments."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from payrexx.models import Subscription

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


class SubscriptionResource:
    """``/Subscription/`` endpoints."""

    def __init__(self, client: PayrexxClient) -> None:
        self._client = client

    def list(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        order_by_start_date: str | None = None,
    ) -> builtins.list[Subscription]:
        """List subscriptions.

        Args:
            order_by_start_date: Sort direction on the start date, as accepted by
                the API's ``orderByStartDate``.
        """
        params: dict[str, Any] = {}
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        if order_by_start_date is not None:
            params["orderByStartDate"] = order_by_start_date
        data = self._client.get("Subscription/", params=params or None)
        rows = data if isinstance(data, builtins.list) else [data] if data else []
        return [Subscription.from_api(row) for row in rows]

    def retrieve(self, subscription_id: int | str) -> Subscription:
        """Read one subscription."""
        data = self._client.get(f"Subscription/{self._client.quote_segment(subscription_id)}/")
        return Subscription.from_api(_unwrap(data))

    def create(
        self,
        *,
        user_id: int | str,
        amount: int,
        currency: str,
        payment_interval: str,
        period: str | None = None,
        cancellation_interval: str | None = None,
        purpose: str | None = None,
        reference_id: str | None = None,
        psp: int | str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Subscription:
        """Create a subscription for an existing Payrexx user.

        Args:
            user_id: The Payrexx user (contact) to bill. A subscription is attached
                to a user, not created from thin air — collect the payment details
                first through a gateway with ``subscription_state=True``.
            amount: Amount per period, in the smallest currency unit.
            payment_interval: ISO 8601 duration, e.g. ``"P1M"`` — see
                [`payrexx.enums.Interval`][payrexx.enums.Interval].
            period: Total duration of the subscription.
            cancellation_interval: Notice period for cancellation.
        """
        payload: dict[str, Any] = {
            "userId": user_id,
            "amount": amount,
            "currency": currency,
            "paymentInterval": payment_interval,
            "period": period,
            "cancellationInterval": cancellation_interval,
            "purpose": purpose,
            "referenceId": reference_id,
            "psp": psp,
        }
        if extra:
            payload.update(extra)
        data = self._client.post("Subscription/", data=payload)
        return Subscription.from_api(_unwrap(data))

    def update(
        self,
        subscription_id: int | str,
        *,
        amount: int | None = None,
        currency: str | None = None,
        payment_interval: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Subscription:
        """Update a subscription.

        Sent as ``PUT``, which is what the PHP SDK maps ``update`` to.
        """
        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "paymentInterval": payment_interval,
        }
        if extra:
            payload.update(extra)
        data = self._client.put(
            f"Subscription/{self._client.quote_segment(subscription_id)}/", data=payload
        )
        return Subscription.from_api(_unwrap(data))

    def cancel(self, subscription_id: int | str) -> Subscription:
        """Cancel a subscription.

        Sent as ``DELETE``: the PHP SDK maps ``cancel`` to ``DELETE``, not ``POST``.
        """
        data = self._client.delete(f"Subscription/{self._client.quote_segment(subscription_id)}/")
        return Subscription.from_api(_unwrap(data))


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, builtins.list):
        return data[0] if data else {}
    return data or {}
