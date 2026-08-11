"""The PaymentProvider resource: which PSPs and methods the account can use."""

from __future__ import annotations

from typing import TYPE_CHECKING

from payrexx.models import PaymentProvider

if TYPE_CHECKING:  # pragma: no cover
    from payrexx.client import PayrexxClient


class PaymentProviderResource:
    """``/PaymentProvider/`` endpoints."""

    def __init__(self, client: PayrexxClient) -> None:
        self._client = client

    def list(self) -> list[PaymentProvider]:
        """List the PSPs configured on the account.

        Read-only and cheap, which makes it the natural probe for
        :meth:`~payrexx.client.PayrexxClient.health_check`. Note that the response
        also carries the account balance, so any API key is enough to read it —
        keys are not scoped per integration despite what the back-office labels
        suggest.
        """
        data = self._client.get("PaymentProvider/")
        rows = data if isinstance(data, list) else [data] if data else []
        return [PaymentProvider.from_api(row) for row in rows]

    def active_payment_methods(self) -> set[str]:
        """Union of the payment methods actually enabled across all PSPs.

        Use this instead of assuming: a method can be supported by the PSP yet
        disabled on the account, and offering a disabled method makes the hosted
        page reject the shopper's choice.
        """
        return {m for p in self.list() for m in p.active_payment_methods}

    def find(self, name_or_id: str | int) -> PaymentProvider | None:
        """Look a PSP up by id or by name, case-insensitively."""
        for provider in self.list():
            if provider.id == name_or_id:
                return provider
            if provider.name.casefold() == str(name_or_id).casefold():
                return provider
        return None
