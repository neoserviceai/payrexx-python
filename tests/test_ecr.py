"""ECR tests: paths, versioning, and the no-blind-retry guarantee."""

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from payrexx import PayrexxClient
from payrexx.client import API_VERSION
from payrexx.errors import (
    PayrexxTransportError,
    ServerError,
    TerminalNotFoundError,
)
from tests.helpers import request_body, request_url

BASE = "https://api.payrexx.com"
V = API_VERSION
SN = "SN-N86-1"


@pytest.fixture
def client():
    return PayrexxClient(instance="demo", api_secret="secret", max_retries=3)


@responses.activate
def test_ecr_calls_use_the_v116_path(client):
    responses.add(
        responses.GET, f"{BASE}/{V}/ecr/{SN}/pair", json={"status": "success", "data": []}
    )
    client.ecr.get_pairing(SN)
    assert "/v1.16/ecr/" in request_url(responses.calls[0])


@responses.activate
def test_pair_sends_the_code_and_optional_cashier_name(client):
    responses.add(
        responses.POST, f"{BASE}/{V}/ecr/{SN}/pair", json={"status": "success", "data": []}
    )
    client.ecr.pair(SN, "QP3U58", cashier_name="Caisse 1")
    body = request_body(responses.calls[0])
    assert "pairingCode=QP3U58" in body
    assert "cashierName=Caisse+1" in body or "cashierName=Caisse%201" in body


@responses.activate
def test_create_payment_sends_amount_in_cents_and_the_reference(client):
    responses.add(
        responses.POST,
        f"{BASE}/{V}/ecr/{SN}/payment",
        json={
            "status": "success",
            "data": {"payment_id": "pay_1", "payment_status": "pending", "slip": []},
        },
    )
    payment = client.ecr.create_payment(
        SN,
        amount=1500,
        currency="CHF",
        payment_method="twint",
        payment_reference="PI-2026-00000001",
        print_slip=True,
    )
    body = request_body(responses.calls[0])
    assert "amount=1500" in body
    assert "paymentMethod=twint" in body
    assert "paymentReference=PI-2026-00000001" in body
    assert "printSlip=1" in body
    assert payment.payment_id == "pay_1"
    assert payment.serial_number == SN
    # Status stays a raw string: Payrexx enumerates no values for this field.
    assert payment.status == "pending"


@responses.activate
def test_terminal_payment_is_never_retried_on_server_error(client):
    """The safety property that protects the customer's card.

    Retrying a terminal charge that may already have gone through is how a shopper
    gets billed twice. The client accepts three retries for idempotent verbs and
    still must not use them here.
    """
    responses.add(responses.POST, f"{BASE}/{V}/ecr/{SN}/payment", status=503)
    with pytest.raises(ServerError):
        client.ecr.create_payment(SN, amount=1500, currency="CHF")
    assert len(responses.calls) == 1


@responses.activate
def test_terminal_payment_is_never_retried_on_transport_error(client):
    responses.add(
        responses.POST, f"{BASE}/{V}/ecr/{SN}/payment", body=RequestsConnectionError("reset")
    )
    with pytest.raises(PayrexxTransportError):
        client.ecr.create_payment(SN, amount=1500, currency="CHF")
    assert len(responses.calls) == 1


@responses.activate
def test_shop_items_are_nested_per_index(client):
    responses.add(
        responses.POST, f"{BASE}/{V}/ecr/{SN}/payment", json={"status": "success", "data": {}}
    )
    client.ecr.create_payment(
        SN, amount=1000, currency="CHF", shop_items=[{"name": "Beer", "price": 10}]
    )
    body = request_body(responses.calls[0])
    assert "shopItems%5B0%5D%5Bname%5D=Beer" in body or "shopItems[0][name]=Beer" in body


@responses.activate
def test_get_payment_reads_a_payment_back(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/ecr/{SN}/payment/pay_1",
        json={"status": "success", "data": {"payment_id": "pay_1", "payment_status": "approved"}},
    )
    assert client.ecr.get_payment(SN, "pay_1").status == "approved"


@responses.activate
def test_slip_accepts_string_list_and_dict_shapes(client):
    for slip, expected in [
        (["line1", "line2"], 2),
        ("single", 1),
        ({"a": "x", "b": "y"}, 2),
    ]:
        responses.reset()
        responses.add(
            responses.GET,
            f"{BASE}/{V}/ecr/{SN}/payment/p",
            json={"status": "success", "data": {"payment_id": "p", "slip": slip}},
        )
        assert len(client.ecr.get_payment(SN, "p").slip) == expected


@responses.activate
def test_unknown_serial_raises_terminal_not_found(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/ecr/NOPE/pair",
        status=404,
        json={"status": "error", "message": "An error occurred: Terminal not found"},
    )
    with pytest.raises(TerminalNotFoundError):
        client.ecr.get_pairing("NOPE")


@responses.activate
def test_cancel_and_void_carry_the_payment_id_in_the_path(client):
    """Follows the official PHP SDK, not the REST reference.

    The reference documents ``POST /ecr/{sn}/payment/cancel`` with the id in the
    body, but the SDK's ``setPaymentId`` assigns ``'payment/' + id`` as the resource
    id, producing ``/ecr/{sn}/payment/{id}/cancel``. Both forms return the same
    error against an unpaired terminal, so live probing could not separate them —
    the SDK wins as the more authoritative source.
    """
    responses.add(
        responses.POST,
        f"{BASE}/{V}/ecr/{SN}/payment/pay_1/cancel",
        json={"status": "success", "data": {"payment_id": "pay_1"}},
    )
    responses.add(
        responses.POST,
        f"{BASE}/{V}/ecr/{SN}/payment/pay_1/void",
        json={"status": "success", "data": {"payment_id": "pay_1"}},
    )
    cancelled = client.ecr.cancel_payment(SN, "pay_1")
    voided = client.ecr.void_payment(SN, "pay_1")

    assert request_url(responses.calls[0]).endswith("payment/pay_1/cancel?instance=demo")
    assert request_url(responses.calls[1]).endswith("payment/pay_1/void?instance=demo")
    # Both now return a parsed payment rather than a raw dict.
    assert cancelled.payment_id == "pay_1"
    assert voided.serial_number == SN


def test_ecr_payment_reads_the_status_the_device_actually_sends() -> None:
    """GET /ecr/{sn}/payment/{id} answers `status`, not the documented `payment_status`.

    Reading only the documented spelling left status as None on every real terminal
    payment — so a finished payment looked like it was still running, and a till would
    have waited on a screen that never changed. Verified against a NexGo N86.
    """
    from payrexx.models import EcrPayment

    assert EcrPayment.from_api({"status": "TERMINATED"}).status == "TERMINATED"
    # The documented spellings still win when present, so a future fix upstream
    # cannot be undone by this fallback.
    assert EcrPayment.from_api({"payment_status": "SUCCESS", "status": "x"}).status == "SUCCESS"


@responses.activate
def test_spaces_are_percent_encoded_not_plus(client) -> None:
    """A space must travel as %20, because Payrexx does not decode "+".

    Sent as "+", a shop item called "Café Neoservice" reaches the terminal's printed
    receipt as "Café+Neoservice" — verified against a NexGo N86 on 2026-08-21. The
    customer is the one who reads that receipt, so the bug is visible where it hurts.
    """
    responses.add(responses.POST, f"{BASE}/{V}/ecr/SN1/payment",
                  json={"status": "success", "data": {}})
    client.ecr.create_payment(
        "SN1", amount=680, currency="CHF",
        shop_items=[client.ecr.shop_item("Café Neoservice", 250, quantity=2)],
    )
    body = request_body(responses.calls[0])
    assert "Caf%C3%A9%20Neoservice" in body
    assert "+" not in body


# --- Receipt fields when the device answers a mapping ------------------------
#
# The device sends `slip` two ways. Early readings were a positional list, so
# `receipt` parsed by index; a real NexGo N86 answers a **mapping**. Flattening
# that mapping into a tuple threw the keys away and every receipt field came back
# empty — on a card payment that had gone through, printed its own slip, and whose
# details the merchant then had to reproduce on their own paper.

_REAL_CARD_SLIP = {
    "aid": "A0000000041010",
    "amount": 100,
    "card_number": "535388******4256",
    "company": "Neoservice Christillin",
    "completed_at": "Aug 22, 2026 02:14:33 PM",
    "created_at": "Aug 22, 2026 02:14:33 PM",
    "currency": "CHF",
    "ext_transaction_id": "ca55cf91-1812-4668-b188-6bde74783aa5",
    "payment_method": {"name": "CARD", "type": "CARD", "group": "CARD"},
    "payment_provider": "MASTERCARD",
    "payment_status": "CANCELED",
    "point_of_sale": "Neoservice Christillin",
    "terminal_name": "Terminal-0506",
    "tip_amount": 0,
    "transaction_id": "",
}


def _card_payment():
    from payrexx.models import EcrPayment

    return EcrPayment.from_api(
        {"paymentId": "p1", "status": "TERMINATED", "slip": _REAL_CARD_SLIP}
    )


def test_receipt_reads_a_mapping_slip_by_name():
    """Every field a card receipt legally needs must survive."""
    receipt = _card_payment().receipt

    assert receipt["masked_pan"] == "535388******4256"
    assert receipt["authorisation"] == "A0000000041010"
    assert receipt["card_scheme"] == "MASTERCARD"
    assert receipt["amount"] == 100
    assert receipt["currency"] == "CHF"
    assert receipt["merchant_name"] == "Neoservice Christillin"
    assert receipt["terminal_label"] == "Terminal-0506"
    assert receipt["payment_method"] == "CARD"
    assert receipt["datetime"] == "Aug 22, 2026 02:14:33 PM"


def test_receipt_never_carries_the_slips_own_status():
    """The slip said CANCELED for a payment that succeeded.

    Observed on a NexGo N86 on 2026-08-22: the printed receipt read RÉUSSI while
    ``slip.payment_status`` read ``CANCELED``. Printing that on the customer's copy
    would contradict the sale it documents, so the outcome comes from the caller.
    """
    receipt = _card_payment().receipt

    assert "status" not in receipt
    assert "CANCELED" not in str(
        {k: v for k, v in receipt.items() if k != "raw_slip"}
    )


def test_positional_slip_still_parses():
    """The list form has not gone away, so it must keep working."""
    from payrexx.models import EcrPayment

    payment = EcrPayment.from_api(
        {"paymentId": "p2", "status": "SUCCESS", "slip": [1500, None, {"code": "CHF"}]}
    )
    assert payment.slip_map == {}
    assert payment.receipt["amount"] == 1500
    assert payment.receipt["currency"] == "CHF"
