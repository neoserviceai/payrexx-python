"""PHP-style form encoding, which is what the Payrexx API actually expects.

Payrexx's own SDKs are written in PHP and post their payloads through
``http_build_query``. The API therefore only understands PHP's bracket notation
for anything that is not a flat scalar:

A list is numerically indexed, and a mapping nests by key::

    {"pm": ["twint", "visa"]}                     ->  pm[0]=twint&pm[1]=visa
    {"fields": {"forename": {"value": "Jean"}}}   ->  fields[forename][value]=Jean

This matters more than it looks. Sending ``pm=twint`` or ``pm[]=twint`` does not
fail: Payrexx answers ``200 OK``, echoes back an empty ``pm`` list, and silently
serves every payment method on the hosted page. A filter that is quietly dropped
lets a shopper pay by a method other than the one the caller recorded, which
breaks reconciliation downstream. Verified against a live account on 2026-08-03.

Encoding every payload through `encode_form` removes that failure mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _stringify(value: Any) -> str:
    """Render a scalar the way PHP's ``http_build_query`` would."""
    if isinstance(value, bool):
        # PHP serialises booleans as 1/0; "true"/"false" are read as truthy strings.
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        # Avoid "1500.0" for an amount that must travel as an integer of cents.
        return str(int(value))
    return str(value)


def _flatten(key: str, value: Any, out: list[tuple[str, str]]) -> None:
    if value is None:
        # Omit rather than send an empty string: Payrexx treats "" as a real value
        # for some fields (e.g. it would blank out a stored contact detail).
        return

    if isinstance(value, Mapping):
        for sub_key, sub_value in value.items():
            _flatten(f"{key}[{sub_key}]", sub_value, out)
        return

    # str/bytes are Sequences too, so they must be excluded explicitly.
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _flatten(f"{key}[{index}]", item, out)
        return

    out.append((key, _stringify(value)))


def encode_form(data: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Flatten ``data`` into ordered name/value pairs for a form body.

    Returns a list of pairs rather than a dict so repeated bracket keys survive,
    and so the ordering stays stable — which keeps request bodies reproducible in
    tests and readable in logs.

    Examples:
        >>> encode_form({"amount": 1500, "currency": "CHF", "pm": ["twint"]})
        [('amount', '1500'), ('currency', 'CHF'), ('pm[0]', 'twint')]
        >>> encode_form({"fields": {"forename": {"value": "Jean"}}})
        [('fields[forename][value]', 'Jean')]
        >>> encode_form({"printSlip": True, "unset": None})
        [('printSlip', '1')]
    """
    out: list[tuple[str, str]] = []
    for key, value in data.items():
        _flatten(key, value, out)
    return out
