"""Typed accessors over `responses` call records.

`responses` types ``request.body`` as ``bytes | str | None`` and bolts ``params``
onto ``PreparedRequest`` at runtime, so reading either straight from a call fails
type checking. These helpers narrow once, here, instead of scattering casts and
ignores through every test — and they fail loudly when a request that was meant to
carry a body turns out not to.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse


def request_body(call: Any) -> str:
    """Return a call's request body as text.

    Raises:
        AssertionError: The request carried no body. A test asserting on body
            content against a bodyless request is a broken test, not a pass.
    """
    body = call.request.body
    assert body is not None, "expected a request body, got none"
    if isinstance(body, bytes):
        return body.decode("utf-8")
    return str(body)


def request_url(call: Any) -> str:
    """Return a call's full request URL."""
    url = call.request.url
    assert url is not None, "expected a request URL, got none"
    return str(url)


def request_params(call: Any) -> dict[str, str]:
    """Return a call's query parameters, parsed from its URL.

    Parsed from the URL rather than read off ``request.params``, which `responses`
    attaches dynamically and which type checkers cannot see.
    """
    query = urlparse(request_url(call)).query
    return {key: values[0] for key, values in parse_qs(query).items()}
