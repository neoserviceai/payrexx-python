"""Gateway tests, built on the real response shape observed on 2026-08-03."""

from typing import Any

import pytest
import responses

from payrexx import PayrexxClient, TransactionStatus
from payrexx.client import API_VERSION
from tests.helpers import request_body

BASE = "https://api.payrexx.com"
V = API_VERSION

# Verbatim shape of a live POST /Gateway/ response.
GATEWAY_JSON: dict[str, Any] = {
    "status": "success",
    "data": [
        {
            "id": 36085448,
            "hash": "aaaa1111bbbb2222cccc3333dddd4444",
            "status": "waiting",
            "referenceId": "PI-TEST-0803-A",
            "amount": 1500,
            "currency": "CHF",
            "createdAt": 1786454809,
            "link": "https://demo.payrexx.com/?payment=aaaa1111bbbb2222cccc3333dddd4444",
            "psp": [],
            "pm": [],
            "invoices": [],
            "vatRate": None,
            "sku": None,
            "preAuthorization": False,
            "applicationFee": None,
            "fields": {},
            "requestId": None,
        }
    ],
}


@pytest.fixture
def client():
    return PayrexxClient(instance="demo", api_secret="secret")


@responses.activate
def test_create_parses_the_live_response_shape(client):
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json=GATEWAY_JSON)
    gw = client.gateway.create(amount=1500, currency="CHF", reference_id="PI-TEST-0803-A")

    assert gw.id == 36085448
    assert gw.status == TransactionStatus.WAITING
    assert gw.reference_id == "PI-TEST-0803-A"
    assert gw.amount == 1500
    assert gw.link.startswith("https://demo.payrexx.com/?payment=")
    assert gw.created_at is not None
    assert gw.created_at.year == 2026
    assert gw.is_paid is False


@responses.activate
def test_payment_method_filter_is_sent_indexed(client):
    """Regression guard for the silent-drop trap.

    ``pm=twint`` and ``pm[]=twint`` both return 200 with an empty ``pm`` and every
    method still on the page. Only ``pm[0]=twint`` is honoured.
    """
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json=GATEWAY_JSON)
    client.gateway.create(amount=500, currency="CHF", payment_methods=["twint"])

    body = request_body(responses.calls[0])
    assert "pm%5B0%5D=twint" in body or "pm[0]=twint" in body
    assert "pm=twint" not in body.replace("pm%5B0%5D=twint", "")


@responses.activate
def test_filter_was_applied_reflects_what_payrexx_kept(client):
    gateway: dict[str, Any] = GATEWAY_JSON["data"][0]
    kept = {"status": "success", "data": [{**gateway, "pm": ["twint"]}]}
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json=kept)
    gw = client.gateway.create(amount=500, currency="CHF", payment_methods=["twint"])
    assert gw.filter_was_applied is True


@responses.activate
def test_filter_was_applied_is_false_when_payrexx_dropped_it(client):
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json=GATEWAY_JSON)  # pm: []
    gw = client.gateway.create(amount=500, currency="CHF", payment_methods=["twint"])
    assert gw.filter_was_applied is False


@responses.activate
def test_nested_contact_fields_are_bracket_encoded(client):
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json=GATEWAY_JSON)
    client.gateway.create(amount=100, currency="CHF", fields={"forename": {"value": "Jean"}})
    body = request_body(responses.calls[0])
    assert "fields%5Bforename%5D%5Bvalue%5D=Jean" in body or "fields[forename][value]=Jean" in body


@responses.activate
def test_extra_can_override_a_mapped_parameter(client):
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json=GATEWAY_JSON)
    client.gateway.create(amount=100, currency="CHF", extra={"currency": "EUR"})
    assert "currency=EUR" in request_body(responses.calls[0])


@responses.activate
def test_retrieve_round_trips(client):
    responses.add(responses.GET, f"{BASE}/{V}/Gateway/36085448/", json=GATEWAY_JSON)
    gw = client.gateway.retrieve(36085448)
    assert gw.reference_id == "PI-TEST-0803-A"


@responses.activate
def test_empty_data_list_does_not_crash(client):
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", json={"status": "success", "data": []})
    gw = client.gateway.create(amount=100, currency="CHF")
    assert gw.id is None
    assert gw.link == ""
