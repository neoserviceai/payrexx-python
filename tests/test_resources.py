"""Tests for the resources modelled on the official PHP SDK.

Every HTTP verb asserted here was read off the SDK's ``Communicator::$methods``
map, because several of them are counter-intuitive and the REST reference does not
state them:

- ``cancel`` is a ``DELETE``, while ``refund``/``capture``/``charge`` are ``POST``
- ``update`` is a ``PUT`` for every model **except** ``Design``, which is a ``POST``
- ``patchUpdate`` is a ``PATCH``
"""

import pytest
import responses

from payrexx import PayrexxClient
from payrexx.client import API_VERSION
from tests.helpers import request_body, request_params, request_url

BASE = f"https://api.payrexx.com/{API_VERSION}"
OK = {"status": "success", "data": [{"id": 1}]}


@pytest.fixture
def client():
    return PayrexxClient(instance="demo", api_secret="secret")


def test_client_pins_a_version_with_specific_status_codes():
    """v1.15 is where Payrexx introduced per-error HTTP status codes.

    The error mapping cannot be trusted below that, so the pinned version must not
    silently drift back to v1.0.
    """
    major, minor = API_VERSION.lstrip("v").split(".")
    assert (int(major), int(minor)) >= (1, 15)


# ----------------------------------------------------------------------
# Transaction — the verb map is the point
# ----------------------------------------------------------------------


@responses.activate
def test_cancel_is_a_delete_not_a_post(client):
    responses.add(responses.DELETE, f"{BASE}/Transaction/7/", json=OK)
    client.transaction.cancel(7)
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_charge_capture_refund_receipt_are_posts_on_their_own_segment(client):
    for action, call in [
        ("charge", lambda: client.transaction.charge(7, amount=100)),
        ("capture", lambda: client.transaction.capture(7)),
        ("refund", lambda: client.transaction.refund(7, amount=50)),
        ("preAuthorize", lambda: client.transaction.pre_authorize(7, amount=100)),
        ("receipt", lambda: client.transaction.send_receipt(7, recipient="a@b.c")),
    ]:
        responses.reset()
        responses.add(responses.POST, f"{BASE}/Transaction/7/{action}", json=OK)
        call()
        assert responses.calls[0].request.method == "POST"
        assert request_url(responses.calls[0]).startswith(f"{BASE}/Transaction/7/{action}")


@responses.activate
def test_list_filters_use_the_sdk_parameter_names(client):
    responses.add(responses.GET, f"{BASE}/Transaction/", json={"status": "success", "data": []})
    client.transaction.list(
        limit=10,
        datetime_utc_greater_than="2026-01-01 00:00:00",
        my_transactions_only=True,
        order_by_time="desc",
    )
    params = request_params(responses.calls[0])
    assert params["filterDatetimeUtcGreaterThan"] == "2026-01-01 00:00:00"
    assert params["filterMyTransactionsOnly"] == "1"
    assert params["orderByTime"] == "desc"


# ----------------------------------------------------------------------
# Subscription
# ----------------------------------------------------------------------


@responses.activate
def test_subscription_update_is_a_put(client):
    responses.add(responses.PUT, f"{BASE}/Subscription/3/", json=OK)
    client.subscription.update(3, amount=2000)
    assert responses.calls[0].request.method == "PUT"


@responses.activate
def test_subscription_cancel_is_a_delete(client):
    responses.add(responses.DELETE, f"{BASE}/Subscription/3/", json=OK)
    client.subscription.cancel(3)
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_subscription_create_sends_iso_interval(client):
    responses.add(responses.POST, f"{BASE}/Subscription/", json=OK)
    client.subscription.create(user_id=42, amount=2000, currency="CHF", payment_interval="P1M")
    body = request_body(responses.calls[0])
    assert "paymentInterval=P1M" in body
    assert "userId=42" in body


@responses.activate
def test_subscription_parses_its_dates_and_active_flag(client):
    responses.add(
        responses.GET,
        f"{BASE}/Subscription/3/",
        json={
            "status": "success",
            "data": [
                {
                    "id": 3,
                    "status": "active",
                    "paymentInterval": "P1M",
                    "start": "2026-01-01",
                    "valid_until": "2026-12-31",
                    "nextPayDate": "2026-09-01",
                }
            ],
        },
    )
    sub = client.subscription.retrieve(3)
    assert sub.is_active is True
    assert sub.payment_interval == "P1M"
    assert sub.valid_until == "2026-12-31"
    assert sub.next_pay_date == "2026-09-01"


# ----------------------------------------------------------------------
# Design — the one model whose update is a POST
# ----------------------------------------------------------------------


@responses.activate
def test_design_update_is_a_post_unlike_every_other_model(client):
    """The PHP SDK special-cases exactly this: `update` is PUT except for Design."""
    responses.add(responses.POST, f"{BASE}/Design/5/", json=OK)
    client.design.update(5, backgroundColor="#ffffff")
    assert responses.calls[0].request.method == "POST"


# ----------------------------------------------------------------------
# Bill
# ----------------------------------------------------------------------


@responses.activate
def test_bill_create_nests_positions(client):
    responses.add(responses.POST, f"{BASE}/Bill/", json=OK)
    client.bill.create(currency="CHF", positions=[{"name": "Consulting", "price": 20000}])
    body = request_body(responses.calls[0])
    assert "positions%5B0%5D%5Bname%5D=Consulting" in body


@responses.activate
def test_bill_patch_uses_the_patch_verb(client):
    responses.add(responses.PATCH, f"{BASE}/Bill/9/", json=OK)
    client.bill.patch(9, note="updated")
    assert responses.calls[0].request.method == "PATCH"


# ----------------------------------------------------------------------
# Payout
# ----------------------------------------------------------------------


@responses.activate
def test_payout_details_hits_the_details_segment(client):
    responses.add(responses.GET, f"{BASE}/Payout/abc/details", json=OK)
    client.payout.details("abc")
    assert request_url(responses.calls[0]).startswith(f"{BASE}/Payout/abc/details")


@responses.activate
def test_payout_parses_transfers_and_fees(client):
    responses.add(
        responses.GET,
        f"{BASE}/Payout/abc/details",
        json={
            "status": "success",
            "data": [
                {
                    "uuid": "abc",
                    "status": "paid",
                    "amount": 10000,
                    "currency": "CHF",
                    "totalFees": 250,
                    "isManualPayout": False,
                    "transfers": [{"amount": 5000}, {"amount": 5000}],
                }
            ],
        },
    )
    payout = client.payout.details("abc")
    assert payout.total_fees == 250
    assert len(payout.transfers) == 2
    assert payout.is_manual_payout is False


# ----------------------------------------------------------------------
# QR code, invoice, page, payment method, auth token
# ----------------------------------------------------------------------


@responses.activate
def test_qr_code_create_and_renders(client):
    responses.add(
        responses.POST,
        f"{BASE}/QrCode/",
        json={
            "status": "success",
            "data": [{"id": 1, "qrCode": "x", "svg": "<svg/>", "png": "iVBO"}],
        },
    )
    qr = client.qr_code.create(webshop_url="https://shop.example.com")
    assert qr.svg == "<svg/>"
    assert qr.png == "iVBO"


@responses.activate
def test_invoice_create_sends_indexed_payment_methods(client):
    responses.add(responses.POST, f"{BASE}/Invoice/", json=OK)
    client.invoice.create(
        title="T", description="D", amount=1000, currency="CHF", payment_methods=["twint"]
    )
    body = request_body(responses.calls[0])
    assert "pm%5B0%5D=twint" in body


@responses.activate
def test_payment_method_list_maps_filters(client):
    responses.add(responses.GET, f"{BASE}/PaymentMethod/", json={"status": "success", "data": []})
    client.payment_method.list(currency="CHF", psp=44)
    params = request_params(responses.calls[0])
    assert params["filterCurrency"] == "CHF"
    assert params["filterPsp"] == "44"


@responses.activate
def test_auth_token_parses_link_and_expiry(client):
    responses.add(
        responses.POST,
        f"{BASE}/AuthToken/",
        json={
            "status": "success",
            "data": [
                {
                    "authToken": "tok",
                    "link": "https://demo.payrexx.com/?token=tok",
                    "authTokenExpirationDate": "2026-08-04 10:00:00",
                }
            ],
        },
    )
    token = client.auth_token.create(user_id=1)
    assert token.auth_token == "tok"
    assert token.expires_at == "2026-08-04 10:00:00"


# ----------------------------------------------------------------------
# Signature check
# ----------------------------------------------------------------------


@responses.activate
def test_signature_check_returns_true_when_accepted(client):
    responses.add(responses.GET, f"{BASE}/SignatureCheck/", json={"status": "success", "data": []})
    assert client.signature_check.check() is True


@responses.activate
def test_signature_check_returns_false_instead_of_raising(client):
    responses.add(
        responses.GET,
        f"{BASE}/SignatureCheck/",
        status=403,
        json={"status": "error", "message": "The API secret is not correct."},
    )
    assert client.signature_check.check() is False


@responses.activate
def test_signature_check_still_propagates_transport_failures(client):
    """A network problem says nothing about the credentials — it must not read as False."""
    from requests.exceptions import ConnectionError as RequestsConnectionError

    from payrexx.errors import PayrexxTransportError

    responses.add(responses.GET, f"{BASE}/SignatureCheck/", body=RequestsConnectionError("x"))
    with pytest.raises(PayrexxTransportError):
        client.signature_check.check()


# ----------------------------------------------------------------------
# ECR corrections taken from the SDK
# ----------------------------------------------------------------------


@responses.activate
def test_ecr_cancel_puts_the_payment_id_in_the_path(client):
    """The SDK's ``setPaymentId`` assigns ``'payment/' + id`` as the resource id,
    so ``cancel`` lands on ``/payment/{id}/cancel`` — not in the request body."""
    responses.add(responses.POST, f"{BASE}/ecr/SN1/payment/pay_9/cancel", json=OK)
    client.ecr.cancel_payment("SN1", "pay_9")
    assert request_url(responses.calls[0]).startswith(f"{BASE}/ecr/SN1/payment/pay_9/cancel")


@responses.activate
def test_ecr_void_puts_the_payment_id_in_the_path(client):
    responses.add(responses.POST, f"{BASE}/ecr/SN1/payment/pay_9/void", json=OK)
    client.ecr.void_payment("SN1", "pay_9")
    assert request_url(responses.calls[0]).startswith(f"{BASE}/ecr/SN1/payment/pay_9/void")


@responses.activate
def test_ecr_payment_methods_is_a_get(client):
    responses.add(responses.GET, f"{BASE}/ecr/SN1/paymentMethods", json=OK)
    client.ecr.payment_methods("SN1")
    assert responses.calls[0].request.method == "GET"


@responses.activate
def test_ecr_create_payment_sends_purpose_and_discount(client):
    responses.add(responses.POST, f"{BASE}/ecr/SN1/payment", json={"status": "success", "data": {}})
    client.ecr.create_payment(
        "SN1",
        amount=1500,
        currency="CHF",
        purpose="Table 4",
        discount={"amount": 100},
        shop_items=[client.ecr.shop_item("Beer", 500, quantity=2, vat=81)],
    )
    body = request_body(responses.calls[0])
    assert "purpose=Table+4" in body or "purpose=Table%204" in body
    assert "discount%5Bamount%5D=100" in body
    assert "shopItems%5B0%5D%5Bquantity%5D=2" in body
    assert "shopItems%5B0%5D%5Bvat%5D=81" in body


@responses.activate
def test_pairing_exposes_the_terminal_configuration(client):
    """The pairing response carries the device's own configuration.

    Reading currency and tipping support off the terminal beats hard-coding a
    per-client assumption in the till.
    """
    responses.add(
        responses.GET,
        f"{BASE}/ecr/SN1/pair",
        json={
            "status": "success",
            "data": [
                {
                    "status": "paired",
                    "cashierName": "Till 1",
                    "configuration": {
                        "currency": "CHF",
                        "language": "fr",
                        "pointOfSaleName": "Boutique",
                        "timezone": "Europe/Zurich",
                        "hasTipping": True,
                    },
                }
            ],
        },
    )
    pairing = client.ecr.get_pairing("SN1")
    assert pairing.paired is True
    assert pairing.cashier_name == "Till 1"
    assert pairing.currency == "CHF"
    assert pairing.language == "fr"
    assert pairing.point_of_sale_name == "Boutique"
    assert pairing.timezone == "Europe/Zurich"
    assert pairing.has_tipping is True


@responses.activate
def test_pairing_tolerates_a_response_without_configuration(client):
    responses.add(responses.GET, f"{BASE}/ecr/SN1/pair", json={"status": "success", "data": []})
    pairing = client.ecr.get_pairing("SN1")
    assert pairing.paired is True
    assert pairing.configuration == {}
    assert pairing.has_tipping is False
    assert pairing.currency is None


# ----------------------------------------------------------------------
# Statuses from the SDK constants
# ----------------------------------------------------------------------


def test_the_three_sdk_only_statuses_exist():
    """`initiated`, `insecure` and `uncaptured` appear in the PHP SDK only."""
    from payrexx import TransactionStatus

    assert TransactionStatus("initiated")
    assert TransactionStatus("insecure")
    assert TransactionStatus("uncaptured")


def test_chargeback_is_kept_even_though_the_sdk_omits_it():
    """The webhook reference documents it; the SDK's constants do not. Keep both."""
    from payrexx import TransactionStatus

    assert TransactionStatus("chargeback").is_final is True


def test_uncaptured_is_final_but_not_successful():
    from payrexx import TransactionStatus

    assert TransactionStatus.UNCAPTURED.is_final is True
    assert TransactionStatus.UNCAPTURED.is_successful is False


def test_insecure_is_not_treated_as_success():
    """The money may have moved while the liability shift did not."""
    from payrexx import TransactionStatus

    assert TransactionStatus.INSECURE.is_successful is False
