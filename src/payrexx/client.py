"""HTTP client for the Payrexx API.

Handles the three things every call needs and that are easy to get wrong:

1. **The ``instance`` query parameter is mandatory on every endpoint**, including
   the ``/ecr/*`` ones where the documentation does not mention it. Omitting it
   returns ``422 Unprocessable Content`` with a message that never names the
   missing parameter. This client appends it automatically.
2. **Bodies must be PHP-style form encoded** (see [`payrexx.encoding`][payrexx.encoding]), or
   list filters such as ``pm`` are silently dropped.
3. **Retries must never be blind.** Payrexx exposes no idempotency key, so a
   retried POST creates a second resource — a duplicate payment link on the
   gateway endpoint, a *second charge* on the terminal endpoint. Only idempotent
   verbs are retried here.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import requests

from payrexx.encoding import encode_form
from payrexx.errors import (
    AuthenticationError,
    InvalidRequestError,
    MissingInstanceError,
    NotFoundError,
    PayrexxAPIError,
    PayrexxError,
    PayrexxTransportError,
    RateLimitError,
    ServerError,
    TerminalNotFoundError,
    TerminalNotPairedError,
)

logger = logging.getLogger("payrexx")

DEFAULT_BASE_URL = "https://api.payrexx.com"

#: Highest version the API serves. ``v1.17`` answers "Version not found", and the
#: official PHP SDK still tops out at ``1.15``.
#:
#: Pinning ``v1.16`` rather than the older ``v1.0`` is deliberate: **v1.15 is where
#: Payrexx introduced specific HTTP status codes for failed requests**. On earlier
#: versions the error mapping in `PayrexxClient._handle_response` cannot be
#: relied on. v1.16 additionally resolves payout aggregates into their underlying
#: transfers on ``GET /Payout/{uuid}/details``.
API_VERSION = "v1.16"

#: Kept as separate names because the ECR and merchant endpoints are documented
#: under different versions. They currently point at the same one.
MERCHANT_API_VERSION = API_VERSION
ECR_API_VERSION = API_VERSION

#: Verbs safe to retry. POST is absent on purpose — see the module docstring.
#: PUT and PATCH are also excluded: Payrexx offers no idempotency guarantee, and a
#: replayed update can clobber a concurrent change.
_RETRYABLE_METHODS = frozenset({"GET", "HEAD", "DELETE"})
_RETRYABLE_STATUSES = frozenset(
    {
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)


class PayrexxClient:
    """Low-level transport plus the resource namespaces.

    Typical use::

        from payrexx import PayrexxClient

        client = PayrexxClient(instance="demo", api_secret="…")
        gateway = client.gateway.create(
            amount=1500, currency="CHF", reference_id="PI-2026-00000001"
        )
        print(gateway.link)

    Args:
        instance: Account name, i.e. the ``<instance>`` in
            ``https://<instance>.payrexx.com``. Required — every endpoint needs it.
        api_secret: The API key from *API & Plugins* in the back office.
        pos_api_secret: Optional separate key for ``/ecr/*`` calls. Accounts can
            hold several keys (e.g. one labelled for POS devices), but they are
            **not scoped**: any key grants full merchant access, balance included.
            Treat a key deployed on a terminal as a full credential. When omitted,
            ``api_secret`` is used for terminal calls too.
        timeout: Per-request timeout in seconds.
        max_retries: Attempts for idempotent verbs on transport errors and 5xx.
        session: Inject a pre-configured `requests.Session` (proxies,
            custom TLS, test doubles).
        base_url: Override the API host, e.g. for a recording proxy.
    """

    def __init__(
        self,
        instance: str,
        api_secret: str,
        *,
        pos_api_secret: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        session: requests.Session | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        if not instance:
            raise MissingInstanceError(
                "instance is required: every Payrexx endpoint needs it as a query "
                "parameter, and its absence surfaces as an opaque HTTP 422."
            )
        if not api_secret:
            raise AuthenticationError("api_secret is required")

        self.instance = instance
        self._api_secret = api_secret
        self._pos_api_secret = pos_api_secret or api_secret
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._owns_session = session is None

        # Imported here to keep the module import graph acyclic.
        from payrexx.resources.ecr import EcrResource
        from payrexx.resources.gateway import GatewayResource
        from payrexx.resources.misc import (
            AuthTokenResource,
            BillResource,
            DesignResource,
            InvoiceResource,
            PageResource,
            PaymentMethodResource,
            PayoutResource,
            QrCodeResource,
            SignatureCheckResource,
        )
        from payrexx.resources.payment_provider import PaymentProviderResource
        from payrexx.resources.subscription import SubscriptionResource
        from payrexx.resources.transaction import TransactionResource

        self.gateway = GatewayResource(self)
        self.transaction = TransactionResource(self)
        self.payment_provider = PaymentProviderResource(self)
        self.ecr = EcrResource(self)
        self.subscription = SubscriptionResource(self)
        self.invoice = InvoiceResource(self)
        self.page = PageResource(self)
        self.bill = BillResource(self)
        self.payout = PayoutResource(self)
        self.qr_code = QrCodeResource(self)
        self.design = DesignResource(self)
        self.payment_method = PaymentMethodResource(self)
        self.signature_check = SignatureCheckResource(self)
        self.auth_token = AuthTokenResource(self)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> PayrexxClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying session, unless it was injected by the caller."""
        if self._owns_session:
            self._session.close()

    def __repr__(self) -> str:
        # Never render the secrets.
        return f"PayrexxClient(instance={self.instance!r}, base_url={self.base_url!r})"

    # ------------------------------------------------------------------
    # Request plumbing
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        api_version: str = MERCHANT_API_VERSION,
        use_pos_secret: bool = False,
    ) -> Any:
        """Perform a request and return the unwrapped ``data`` payload.

        Payrexx wraps every response in ``{"status": …, "data": […]}``. On success
        this returns the ``data`` value as-is (usually a list, even for a single
        object); on failure it raises the matching `PayrexxError` subclass.
        """
        method = method.upper()
        url = f"{self.base_url}/{api_version}/{path.lstrip('/')}"

        query = {"instance": self.instance}
        if params:
            query.update({k: v for k, v in params.items() if v is not None})

        headers = {
            "X-API-KEY": self._pos_api_secret if use_pos_secret else self._api_secret,
            "Accept": "application/json",
        }

        # Percent-encoded by hand rather than handed to requests as a list of pairs.
        # requests uses quote_plus, which writes a space as "+" — legal in
        # x-www-form-urlencoded, but Payrexx stores the value without decoding it, so
        # a shop item called "Café Neoservice" reaches the terminal's printed receipt
        # as "Café+Neoservice". Observed on a NexGo N86, 2026-08-21. RFC 3986 escaping
        # ("%20") survives their round trip intact.
        body = None
        if data:
            pairs = encode_form(data)
            body = "&".join(
                f"{quote(key, safe='')}={quote(value, safe='')}" for key, value in pairs
            )
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        attempts = self.max_retries + 1 if method in _RETRYABLE_METHODS else 1
        last_transport_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=query,
                    data=body,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_transport_error = exc
                if attempt < attempts:
                    logger.warning(
                        "payrexx transport error on %s %s (attempt %d/%d): %s",
                        method,
                        path,
                        attempt,
                        attempts,
                        exc,
                    )
                    continue
                raise PayrexxTransportError(
                    f"request failed without an HTTP response: {exc}",
                    method=method,
                    path=path,
                ) from exc

            if response.status_code in _RETRYABLE_STATUSES and attempt < attempts:
                logger.warning(
                    "payrexx %s on %s %s (attempt %d/%d), retrying",
                    response.status_code,
                    method,
                    path,
                    attempt,
                    attempts,
                )
                continue

            return self._handle_response(response, method=method, path=path)

        # Unreachable: the loop either returns or raises.
        raise PayrexxTransportError(  # pragma: no cover
            f"exhausted retries: {last_transport_error}", method=method, path=path
        )

    def _handle_response(self, response: requests.Response, *, method: str, path: str) -> Any:
        status = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        message = payload.get("message") or response.text.strip() or f"HTTP {status}"
        ctx = {"status_code": status, "payload": payload, "method": method, "path": path}

        if status == HTTPStatus.FORBIDDEN:
            # Payrexx overloads 403 three ways: a bad secret, a terminal that is not
            # paired, and a WAF rate-limit ban. Telling them apart matters — an
            # unpaired terminal reported as a rate limit sends you looking at request
            # volume instead of at the device menu.
            lowered = message.lower()
            if "secret" in lowered:
                raise AuthenticationError(message, **ctx)
            if "paired" in lowered or "pairing" in lowered:
                raise TerminalNotPairedError(message, **ctx)
            raise RateLimitError(message, **ctx)
        if status == HTTPStatus.METHOD_NOT_ALLOWED:
            # The documented first symptom of exceeding 600 requests / 5 minutes.
            raise RateLimitError(
                f"{message} — Payrexx answers 405 then 403 when the rate limit "
                f"(~600 requests / 5 minutes) is exceeded",
                **ctx,
            )
        if status == HTTPStatus.NOT_FOUND:
            if "terminal" in message.lower():
                raise TerminalNotFoundError(message, **ctx)
            raise NotFoundError(message, **ctx)
        if status == HTTPStatus.UNPROCESSABLE_ENTITY:
            raise InvalidRequestError(
                f"{message} — with this client `instance` is always sent, so a 422 "
                f"usually points at a missing or malformed body field",
                **ctx,
            )
        if status == HTTPStatus.BAD_REQUEST:
            raise InvalidRequestError(message, **ctx)
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise ServerError(message, **ctx)
        if status >= HTTPStatus.MULTIPLE_CHOICES:
            raise PayrexxError(message, **ctx)

        if isinstance(payload, dict) and payload.get("status") == "error":
            # A 200 carrying an error envelope; seen on some validation paths.
            raise PayrexxAPIError(message, **ctx)

        return payload.get("data") if isinstance(payload, dict) else payload

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> Any:
        """Get."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        """Post."""
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        """Put."""
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        """Patch."""
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        """Delete the record. Irreversible."""
        return self.request("DELETE", path, **kwargs)

    @staticmethod
    def quote_segment(value: str | int) -> str:
        """Percent-encode a path segment such as a terminal serial number."""
        return quote(str(value), safe="")

    def health_check(self) -> dict[str, Any]:
        """Cheap probe of credentials and reachability.

        Calls the payment-provider endpoint, which is read-only and returns the
        account's balance. Never raises — returns ``{"ok": False, "error": …}`` so
        it can back a monitoring endpoint.
        """
        try:
            providers = self.payment_provider.list()
        except PayrexxError as exc:
            return {"ok": False, "instance": self.instance, "error": str(exc)}
        return {
            "ok": True,
            "instance": self.instance,
            "providers": [p.name for p in providers],
            "active_payment_methods": sorted(
                {m for p in providers for m in p.active_payment_methods}
            ),
        }
