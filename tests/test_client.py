"""Client tests: instance injection, error mapping, retry policy."""

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from payrexx import PayrexxClient
from payrexx.client import API_VERSION
from payrexx.errors import (
    AuthenticationError,
    InvalidRequestError,
    MissingInstanceError,
    PayrexxAPIError,
    PayrexxTransportError,
    RateLimitError,
    ServerError,
    TerminalNotFoundError,
)
from tests.helpers import request_params, request_url

BASE = "https://api.payrexx.com"
V = API_VERSION


@pytest.fixture
def client():
    return PayrexxClient(instance="demo", api_secret="secret")


def test_instance_is_required_up_front():
    # Failing at construction beats discovering it as an opaque 422 mid-payment.
    with pytest.raises(MissingInstanceError):
        PayrexxClient(instance="", api_secret="secret")


def test_api_secret_is_required():
    with pytest.raises(AuthenticationError):
        PayrexxClient(instance="demo", api_secret="")


def test_repr_does_not_leak_the_secret(client):
    assert "secret" not in repr(client)


@responses.activate
def test_instance_is_injected_on_every_call(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/PaymentProvider/",
        json={"status": "success", "data": []},
    )
    client.payment_provider.list()
    assert request_params(responses.calls[0])["instance"] == "demo"


@responses.activate
def test_instance_is_injected_on_ecr_calls_too(client):
    # The ECR docs omit it, but Payrexx returns 422 without it.
    responses.add(
        responses.GET,
        f"{BASE}/{V}/ecr/SN123/pair",
        json={"status": "success", "data": []},
    )
    client.ecr.get_pairing("SN123")
    assert request_params(responses.calls[0])["instance"] == "demo"


@responses.activate
def test_bad_secret_maps_to_authentication_error(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/PaymentProvider/",
        status=403,
        json={"status": "error", "message": "An error occurred: The API secret is not correct."},
    )
    with pytest.raises(AuthenticationError):
        client.payment_provider.list()


@responses.activate
def test_403_without_secret_wording_is_a_rate_limit(client):
    # Payrexx reuses 403 for the WAF ban that follows sustained over-limit traffic.
    responses.add(
        responses.GET, f"{BASE}/{V}/PaymentProvider/", status=403, json={"message": "Forbidden"}
    )
    with pytest.raises(RateLimitError):
        client.payment_provider.list()


@responses.activate
def test_405_is_reported_as_a_rate_limit(client):
    responses.add(
        responses.GET, f"{BASE}/{V}/PaymentProvider/", status=405, json={"message": "Not allowed"}
    )
    with pytest.raises(RateLimitError, match="600 requests"):
        client.payment_provider.list()


@responses.activate
def test_unknown_terminal_maps_to_terminal_not_found(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/ecr/NOPE/pair",
        status=404,
        json={"status": "error", "message": "An error occurred: Terminal not found"},
    )
    with pytest.raises(TerminalNotFoundError):
        client.ecr.get_pairing("NOPE")


@responses.activate
def test_422_mentions_the_body_since_instance_is_always_sent(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/PaymentProvider/",
        status=422,
        json={
            "status": "error",
            "reason": "",
            "message": "An error occurred: Unprocessable Content",
        },
    )
    with pytest.raises(InvalidRequestError, match="body field"):
        client.payment_provider.list()


@responses.activate
def test_error_envelope_on_a_200_still_raises(client):
    responses.add(
        responses.GET,
        f"{BASE}/{V}/PaymentProvider/",
        status=200,
        json={"status": "error", "message": "nope"},
    )
    with pytest.raises(PayrexxAPIError, match="nope"):
        client.payment_provider.list()


@responses.activate
def test_get_is_retried_on_server_error(client):
    responses.add(responses.GET, f"{BASE}/{V}/PaymentProvider/", status=502)
    responses.add(
        responses.GET, f"{BASE}/{V}/PaymentProvider/", json={"status": "success", "data": []}
    )
    client.payment_provider.list()
    assert len(responses.calls) == 2


@responses.activate
def test_post_is_never_retried():
    """The core safety property: no idempotency key means no silent duplicates.

    A retried POST would create a second gateway — or, on a terminal, a second
    charge. One attempt, then surface the uncertainty to the caller.
    """
    client = PayrexxClient(instance="demo", api_secret="secret", max_retries=3)
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", status=503)
    with pytest.raises(ServerError):
        client.gateway.create(amount=100, currency="CHF")
    assert len(responses.calls) == 1


@responses.activate
def test_transport_error_is_distinguishable_from_a_rejection():
    """An unknown outcome must not look like a failure.

    On the terminal endpoint this distinction decides whether it is safe to act:
    a rejection means nothing was charged, a transport error means we do not know.
    """
    client = PayrexxClient(instance="demo", api_secret="secret", max_retries=0)
    responses.add(responses.POST, f"{BASE}/{V}/Gateway/", body=RequestsConnectionError("boom"))
    with pytest.raises(PayrexxTransportError):
        client.gateway.create(amount=100, currency="CHF")


@responses.activate
def test_pos_secret_is_used_for_ecr_when_supplied():
    client = PayrexxClient(instance="demo", api_secret="merchant", pos_api_secret="pos")
    responses.add(responses.GET, f"{BASE}/{V}/ecr/SN1/pair", json={"status": "success", "data": []})
    responses.add(
        responses.GET, f"{BASE}/{V}/PaymentProvider/", json={"status": "success", "data": []}
    )
    client.ecr.get_pairing("SN1")
    client.payment_provider.list()
    assert responses.calls[0].request.headers["X-API-KEY"] == "pos"
    assert responses.calls[1].request.headers["X-API-KEY"] == "merchant"


@responses.activate
def test_serial_numbers_are_percent_encoded(client):
    responses.add(
        responses.GET, f"{BASE}/{V}/ecr/a%2Fb/pair", json={"status": "success", "data": []}
    )
    client.ecr.get_pairing("a/b")
    assert "a%2Fb" in request_url(responses.calls[0])


@responses.activate
def test_health_check_reports_failure_instead_of_raising(client):
    responses.add(responses.GET, f"{BASE}/{V}/PaymentProvider/", status=403, json={"message": "x"})
    result = client.health_check()
    assert result["ok"] is False
    assert "error" in result
