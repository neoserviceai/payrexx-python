"""Webhook tests: signature scheme, parsing, derived event id."""

import hashlib
import hmac
import json

import pytest

from payrexx import (
    TransactionStatus,
    TransactionType,
    WebhookSignatureError,
    compute_signature,
    parse_webhook,
    verify_signature,
)

KEY = "signing-key"

TX = {
    "transaction": {
        "id": 1234,
        "uuid": "1122aabb",
        "status": "confirmed",
        "amount": 1000,
        "referenceId": "PI-2026-00000001",
        "type": "POS-Terminal",
        "mode": "TEST",
        "time": "2026-08-03 10:00:00",
        "posSerialNumber": "SN-N86-1",
        "posTerminalName": "Caisse 1",
        "refundable": True,
        "partiallyRefundable": True,
        "payrexxFee": 25,
        "invoice": {"currency": "CHF", "refundedAmount": 0, "referenceId": "PI-2026-00000001"},
    }
}


def _body(payload=None) -> bytes:
    return json.dumps(payload or TX).encode("utf-8")


def _sign(body: bytes, key: str = KEY) -> str:
    return hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_signature_is_lowercase_hex_over_the_raw_body():
    body = _body()
    sig = compute_signature(body, KEY)
    assert sig == sig.lower()
    assert len(sig) == 64          # hex, not base64 (which would be 44 chars)
    assert sig == _sign(body)


def test_signing_key_is_used_as_utf8_text_not_base64():
    # A base64-looking key must still be treated as literal text.
    key = "c2VjcmV0"
    body = b"{}"
    assert compute_signature(body, key) == hmac.new(
        key.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def test_reserialising_the_body_changes_the_signature():
    """Why the raw body must be used: any re-encoding invalidates the HMAC.

    Compact separators are what an HTTP sender typically emits, while ``json.dumps``
    defaults to ``", "`` / ``": "``. Round-tripping through a dict therefore changes
    the bytes without changing the meaning — and breaks the signature.
    """
    original = b'{"a":1,"b":2}'
    reserialised = json.dumps(json.loads(original)).encode("utf-8")
    assert original != reserialised
    assert compute_signature(original, KEY) != compute_signature(reserialised, KEY)


def test_verify_accepts_a_good_signature():
    body = _body()
    assert verify_signature(body, _sign(body), KEY) is True


def test_verify_rejects_wrong_key_missing_header_and_empty_key():
    body = _body()
    assert verify_signature(body, _sign(body, "other"), KEY) is False
    assert verify_signature(body, None, KEY) is False
    assert verify_signature(body, _sign(body), "") is False


def test_verify_tolerates_surrounding_whitespace_and_uppercase():
    body = _body()
    assert verify_signature(body, f"  {_sign(body).upper()}  ", KEY) is True


def test_parse_raises_on_a_bad_signature_by_default():
    body = _body()
    with pytest.raises(WebhookSignatureError):
        parse_webhook(body, headers={"X-Webhook-Signature": "deadbeef"}, signing_key=KEY)


def test_parse_can_be_told_not_to_enforce():
    event = parse_webhook(
        _body(),
        headers={"X-Webhook-Signature": "deadbeef"},
        signing_key=KEY,
        require_signature=False,
    )
    assert event.signature_valid is False


def test_signature_valid_is_none_without_a_key():
    assert parse_webhook(_body()).signature_valid is None


def test_header_lookup_is_case_insensitive():
    body = _body()
    event = parse_webhook(
        body, headers={"x-webhook-signature": _sign(body)}, signing_key=KEY
    )
    assert event.signature_valid is True


def test_transaction_is_parsed_with_channel_and_pos_details():
    event = parse_webhook(_body())
    tx = event.transaction
    assert tx is not None
    assert tx.status == TransactionStatus.CONFIRMED
    assert tx.type == TransactionType.POS_TERMINAL
    assert event.channel == TransactionType.POS_TERMINAL
    assert tx.reference_id == "PI-2026-00000001"
    assert tx.currency == "CHF"
    assert tx.pos_serial_number == "SN-N86-1"
    assert tx.refundable_amount == 1000


def test_event_id_is_stable_across_retries():
    """Payrexx retries up to 10 times over 24 h; all must dedupe to one id."""
    first = parse_webhook(_body()).event_id
    again = parse_webhook(_body()).event_id
    assert first == again == "payrexx_1122aabb_confirmed"


def test_event_id_differs_per_status_change():
    waiting = json.loads(json.dumps(TX))
    waiting["transaction"]["status"] = "waiting"
    assert parse_webhook(_body(waiting)).event_id != parse_webhook(_body()).event_id


def test_event_id_is_none_without_a_transaction():
    assert parse_webhook(b'{"subscription": {"id": 1}}').event_id is None


def test_form_encoded_body_is_accepted():
    event = parse_webhook(
        b"transaction%5Buuid%5D=abc&transaction%5Bstatus%5D=confirmed",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert event.payload  # decoded without raising


def test_unparseable_body_does_not_raise():
    assert parse_webhook(b"\xff\xfe not json").transaction is None


def test_disputed_and_chargeback_are_flagged_separately():
    for status in ("chargeback", "disputed"):
        payload = json.loads(json.dumps(TX))
        payload["transaction"]["status"] = status
        tx = parse_webhook(_body(payload)).transaction
        assert tx.is_disputed is True
        # Neither is a refund: mapping them onto one would misstate the books.
        assert tx.status != TransactionStatus.REFUNDED


def test_unknown_status_is_passed_through_untouched():
    payload = json.loads(json.dumps(TX))
    payload["transaction"]["status"] = "some-new-status"
    assert parse_webhook(_body(payload)).transaction.status == "some-new-status"


def test_partial_refund_reduces_the_refundable_amount():
    payload = json.loads(json.dumps(TX))
    payload["transaction"]["status"] = "partially-refunded"
    payload["transaction"]["invoice"]["refundedAmount"] = 400
    tx = parse_webhook(_body(payload)).transaction
    assert tx.refunded_amount == 400
    assert tx.refundable_amount == 600


def test_over_refund_never_reports_a_negative_amount():
    payload = json.loads(json.dumps(TX))
    payload["transaction"]["invoice"]["refundedAmount"] = 5000
    assert parse_webhook(_body(payload)).transaction.refundable_amount == 0


def test_final_and_successful_flags():
    assert TransactionStatus.CONFIRMED.is_final is True
    assert TransactionStatus.CONFIRMED.is_successful is True
    assert TransactionStatus.WAITING.is_final is False
    assert TransactionStatus.REFUND_PENDING.is_final is False
    assert TransactionStatus.EXPIRED.is_final is True
