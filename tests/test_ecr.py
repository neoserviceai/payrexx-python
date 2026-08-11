"""ECR tests: paths, versioning, and the no-blind-retry guarantee."""

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from payrexx import PayrexxClient
from payrexx.errors import (
    PayrexxTransportError,
    ServerError,
    TerminalNotFoundError,
)

BASE = "https://api.payrexx.com"
SN = "SN-N86-1"


@pytest.fixture
def client():
    return PayrexxClient(instance="neoservice", api_secret="secret", max_retries=3)


@responses.activate
def test_ecr_calls_use_the_v116_path(client):
    responses.add(
        responses.GET, f"{BASE}/v1.16/ecr/{SN}/pair", json={"status": "success", "data": []}
    )
    client.ecr.get_pairing(SN)
    assert "/v1.16/ecr/" in responses.calls[0].request.url


@responses.activate
def test_pair_sends_the_code_and_optional_cashier_name(client):
    responses.add(
        responses.POST, f"{BASE}/v1.16/ecr/{SN}/pair", json={"status": "success", "data": []}
    )
    client.ecr.pair(SN, "QP3U58", cashier_name="Caisse 1")
    body = responses.calls[0].request.body
    assert "pairingCode=QP3U58" in body
    assert "cashierName=Caisse+1" in body or "cashierName=Caisse%201" in body


@responses.activate
def test_create_payment_sends_amount_in_cents_and_the_reference(client):
    responses.add(
        responses.POST,
        f"{BASE}/v1.16/ecr/{SN}/payment",
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
    body = responses.calls[0].request.body
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
    responses.add(responses.POST, f"{BASE}/v1.16/ecr/{SN}/payment", status=503)
    with pytest.raises(ServerError):
        client.ecr.create_payment(SN, amount=1500, currency="CHF")
    assert len(responses.calls) == 1


@responses.activate
def test_terminal_payment_is_never_retried_on_transport_error(client):
    responses.add(
        responses.POST, f"{BASE}/v1.16/ecr/{SN}/payment", body=RequestsConnectionError("reset")
    )
    with pytest.raises(PayrexxTransportError):
        client.ecr.create_payment(SN, amount=1500, currency="CHF")
    assert len(responses.calls) == 1


@responses.activate
def test_shop_items_are_nested_per_index(client):
    responses.add(
        responses.POST, f"{BASE}/v1.16/ecr/{SN}/payment", json={"status": "success", "data": {}}
    )
    client.ecr.create_payment(
        SN, amount=1000, currency="CHF", shop_items=[{"name": "Beer", "price": 10}]
    )
    body = responses.calls[0].request.body
    assert "shopItems%5B0%5D%5Bname%5D=Beer" in body or "shopItems[0][name]=Beer" in body


@responses.activate
def test_get_payment_reads_a_payment_back(client):
    responses.add(
        responses.GET,
        f"{BASE}/v1.16/ecr/{SN}/payment/pay_1",
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
            f"{BASE}/v1.16/ecr/{SN}/payment/p",
            json={"status": "success", "data": {"payment_id": "p", "slip": slip}},
        )
        assert len(client.ecr.get_payment(SN, "p").slip) == expected


@responses.activate
def test_unknown_serial_raises_terminal_not_found(client):
    responses.add(
        responses.GET,
        f"{BASE}/v1.16/ecr/NOPE/pair",
        status=404,
        json={"status": "error", "message": "An error occurred: Terminal not found"},
    )
    with pytest.raises(TerminalNotFoundError):
        client.ecr.get_pairing("NOPE")


@responses.activate
def test_cancel_and_void_target_their_own_endpoints(client):
    responses.add(
        responses.POST, f"{BASE}/v1.16/ecr/{SN}/payment/cancel", json={"status": "success"}
    )
    responses.add(
        responses.POST, f"{BASE}/v1.16/ecr/{SN}/payment/void", json={"status": "success"}
    )
    client.ecr.cancel_payment(SN, "pay_1")
    client.ecr.void_payment(SN, "pay_1")
    assert responses.calls[0].request.url.endswith("payment/cancel?instance=neoservice")
    assert responses.calls[1].request.url.endswith("payment/void?instance=neoservice")
