"""Coverage for the paths the behavioural tests do not reach.

Deliberately mechanical: every public method gets exercised at least once so a
signature that stops matching the transport, or a parse helper that raises on a
shape Payrexx really sends, fails here rather than in production.
"""

from __future__ import annotations

from typing import Any

import pytest
import responses

from payrexx import PayrexxClient
from payrexx.client import API_VERSION
from payrexx.models import (
    AuthToken,
    Bill,
    Design,
    EcrPayment,
    Invoice,
    Page,
    PaymentMethodInfo,
    PaymentProvider,
    Payout,
    QrCode,
    Subscription,
    Transaction,
)
from tests.helpers import request_body, request_params, request_url

BASE = f"https://api.payrexx.com/{API_VERSION}"
OK: dict[str, Any] = {"status": "success", "data": [{"id": 1}]}
EMPTY: dict[str, Any] = {"status": "success", "data": []}


@pytest.fixture
def client():
    return PayrexxClient(instance="demo", api_secret="secret")


# ----------------------------------------------------------------------
# Payment providers
# ----------------------------------------------------------------------

PROVIDERS: dict[str, Any] = {
    "status": "success",
    "data": [
        {
            "id": 44,
            "name": "Payrexx Pay",
            "paymentMethods": ["visa", "twint", "reka"],
            "activePaymentMethods": ["visa", "twint"],
            "availableBalance": [{"currency": "CHF", "amount": "0.00"}],
        },
        {"id": 27, "name": "paiement anticipé", "paymentMethods": [], "activePaymentMethods": []},
    ],
}


@responses.activate
def test_active_payment_methods_unions_across_providers(client):
    responses.add(responses.GET, f"{BASE}/PaymentProvider/", json=PROVIDERS)
    assert client.payment_provider.active_payment_methods() == {"visa", "twint"}


@responses.activate
def test_find_provider_by_id_and_by_name_case_insensitively(client):
    responses.add(responses.GET, f"{BASE}/PaymentProvider/", json=PROVIDERS)
    responses.add(responses.GET, f"{BASE}/PaymentProvider/", json=PROVIDERS)
    responses.add(responses.GET, f"{BASE}/PaymentProvider/", json=PROVIDERS)
    assert client.payment_provider.find(44) is not None
    found = client.payment_provider.find("PAYREXX PAY")
    assert found is not None
    assert found.id == 44
    assert client.payment_provider.find("nope") is None


def test_provider_supports_reflects_active_not_merely_available():
    """`reka` is supported by the PSP but not switched on — offering it would fail."""
    provider = PaymentProvider.from_api(PROVIDERS["data"][0])
    assert provider.supports("twint") is True
    assert provider.supports("reka") is False


@responses.activate
def test_health_check_reports_providers_and_methods(client):
    responses.add(responses.GET, f"{BASE}/PaymentProvider/", json=PROVIDERS)
    result = client.health_check()
    assert result["ok"] is True
    assert result["providers"] == ["Payrexx Pay", "paiement anticipé"]
    assert result["active_payment_methods"] == ["twint", "visa"]


# ----------------------------------------------------------------------
# Gateway — the paths behavioural tests skip
# ----------------------------------------------------------------------


@responses.activate
def test_gateway_delete(client):
    responses.add(responses.DELETE, f"{BASE}/Gateway/9/", json=OK)
    client.gateway.delete(9)
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_gateway_find_by_reference_reads_the_transaction_list(client):
    responses.add(
        responses.GET,
        f"{BASE}/Transaction/",
        json={
            "status": "success",
            "data": [
                {
                    "id": 1,
                    "uuid": "u1",
                    "referenceId": "WANTED",
                    "status": "confirmed",
                    "invoice": {"paymentLink": "https://demo.payrexx.com/?payment=u1"},
                },
                {"id": 2, "uuid": "u2", "referenceId": "OTHER", "status": "waiting"},
            ],
        },
    )
    found = client.gateway.find_by_reference("WANTED")
    assert len(found) == 1
    assert found[0].reference_id == "WANTED"
    assert found[0].link.endswith("payment=u1")


@responses.activate
def test_gateway_create_passes_every_optional_field_through(client):
    responses.add(responses.POST, f"{BASE}/Gateway/", json=OK)
    client.gateway.create(
        amount=1000,
        currency="CHF",
        basket=[{"name": "Item", "quantity": 1, "amount": 1000}],
        button_text="Pay now",
        success_message="Thanks",
        skip_result_page=True,
        is_price_exclusive_vat=False,
        customer_statement_descriptor="DEMO SHOP",
        look_and_feel_profile="42",
        validity=60,
        return_app="myapp://done",
        qr_code_session_id="sess_1",
        reserve_on_authorization=True,
        subscription_state=True,
        subscription_interval="P1M",
        subscription_period="P1Y",
        subscription_cancellation_interval="P1M",
        subscription_period_min_amount=500,
        psp=[44],
        vat_rate=8.1,
        sku="SKU-1",
        language="fr",
    )
    body = request_body(responses.calls[0])
    # "%20", not "+": Payrexx stores form values without decoding "+", so a space sent
    # that way reaches a printed terminal receipt as a literal plus sign.
    assert "buttonText=Pay%20now" in body
    assert "skipResultPage=1" in body
    assert "isPriceExclusiveVat=0" in body
    assert "basket%5B0%5D%5Bname%5D=Item" in body
    assert "psp%5B0%5D=44" in body
    assert "subscriptionInterval=P1M" in body


# ----------------------------------------------------------------------
# Subscription
# ----------------------------------------------------------------------


@responses.activate
def test_subscription_list_passes_its_params(client):
    responses.add(responses.GET, f"{BASE}/Subscription/", json=EMPTY)
    client.subscription.list(offset=10, limit=5, order_by_start_date="desc")
    params = request_params(responses.calls[0])
    assert params["offset"] == "10"
    assert params["limit"] == "5"
    assert params["orderByStartDate"] == "desc"


@responses.activate
def test_subscription_create_and_update_accept_extra(client):
    responses.add(responses.POST, f"{BASE}/Subscription/", json=OK)
    responses.add(responses.PUT, f"{BASE}/Subscription/1/", json=OK)
    client.subscription.create(
        user_id=1,
        amount=100,
        currency="CHF",
        payment_interval="P1M",
        period="P1Y",
        cancellation_interval="P1M",
        purpose="p",
        reference_id="r",
        psp=44,
        extra={"custom": "x"},
    )
    client.subscription.update(
        1, amount=200, currency="CHF", payment_interval="P1M", extra={"custom": "y"}
    )
    assert "custom=x" in request_body(responses.calls[0])
    assert "custom=y" in request_body(responses.calls[1])


# ----------------------------------------------------------------------
# Transaction
# ----------------------------------------------------------------------


@responses.activate
def test_transaction_list_offset_and_less_than_filter(client):
    responses.add(responses.GET, f"{BASE}/Transaction/", json=EMPTY)
    client.transaction.list(
        offset=5, datetime_utc_less_than="2026-12-31 23:59:59", my_transactions_only=False
    )
    params = request_params(responses.calls[0])
    assert params["offset"] == "5"
    assert params["filterDatetimeUtcLessThan"] == "2026-12-31 23:59:59"
    assert params["filterMyTransactionsOnly"] == "0"


@responses.activate
def test_transaction_retrieve_and_find_by_reference(client):
    responses.add(
        responses.GET,
        f"{BASE}/Transaction/3/",
        json={"status": "success", "data": [{"id": 3, "referenceId": "R"}]},
    )
    responses.add(
        responses.GET,
        f"{BASE}/Transaction/",
        json={"status": "success", "data": [{"id": 3, "referenceId": "R"}]},
    )
    assert client.transaction.retrieve(3).reference_id == "R"
    assert len(client.transaction.find_by_reference("R")) == 1


@responses.activate
def test_refund_and_capture_without_amount_send_no_body(client):
    responses.add(responses.POST, f"{BASE}/Transaction/3/refund", json=OK)
    responses.add(responses.POST, f"{BASE}/Transaction/3/capture", json=OK)
    client.transaction.refund(3)
    client.transaction.capture(3)
    assert responses.calls[0].request.body is None
    assert responses.calls[1].request.body is None


@responses.activate
def test_send_receipt_without_recipient_sends_no_body(client):
    responses.add(responses.POST, f"{BASE}/Transaction/3/receipt", json=OK)
    client.transaction.send_receipt(3)
    assert responses.calls[0].request.body is None


@responses.activate
def test_charge_and_pre_authorize_accept_extra(client):
    responses.add(responses.POST, f"{BASE}/Transaction/3/charge", json=OK)
    responses.add(responses.POST, f"{BASE}/Transaction/3/preAuthorize", json=OK)
    client.transaction.charge(
        3,
        amount=1,
        currency="CHF",
        purpose="p",
        reference_id="r",
        vat_rate=8.1,
        fields={"a": {"value": "b"}},
        extra={"z": 1},
    )
    client.transaction.pre_authorize(
        3, amount=1, currency="CHF", purpose="p", reference_id="r", extra={"z": 2}
    )
    assert "z=1" in request_body(responses.calls[0])
    assert "z=2" in request_body(responses.calls[1])


# ----------------------------------------------------------------------
# Invoice, Page, Bill, Payout, QrCode, Design, PaymentMethod, AuthToken
# ----------------------------------------------------------------------


@responses.activate
def test_invoice_retrieve_and_delete(client):
    responses.add(responses.GET, f"{BASE}/Invoice/1/", json=OK)
    responses.add(responses.DELETE, f"{BASE}/Invoice/1/", json=OK)
    client.invoice.retrieve(1)
    client.invoice.delete(1)
    assert responses.calls[1].request.method == "DELETE"


@responses.activate
def test_invoice_create_full(client):
    responses.add(responses.POST, f"{BASE}/Invoice/", json=OK)
    client.invoice.create(
        title="T",
        description="D",
        amount=1,
        currency="CHF",
        reference_id="r",
        purpose="p",
        name="n",
        vat_rate=8.1,
        sku="s",
        expiration_date="2026-12-31",
        button_text="b",
        psp=[44],
        pre_authorization=True,
        reservation=False,
        success_redirect_url="https://a",
        failed_redirect_url="https://b",
        fields={"x": {"value": "y"}},
        subscription_state=True,
        subscription_interval="P1M",
        subscription_period="P1Y",
        subscription_cancellation_interval="P1M",
        extra={"k": "v"},
    )
    body = request_body(responses.calls[0])
    assert "expirationDate=2026-12-31" in body
    assert "k=v" in body


@responses.activate
def test_page_list_retrieve_create(client):
    responses.add(responses.GET, f"{BASE}/Page/", json=OK)
    responses.add(responses.GET, f"{BASE}/Page/1/", json=OK)
    responses.add(responses.POST, f"{BASE}/Page/", json=OK)
    assert len(client.page.list()) == 1
    client.page.retrieve(1)
    client.page.create(
        title="T",
        description="D",
        amount=1,
        currency="CHF",
        name="n",
        purpose="p",
        psp=[44],
        pre_authorization=True,
        reservation=True,
        fields={"a": {"value": "b"}},
        extra={"k": "v"},
    )
    assert "k=v" in request_body(responses.calls[2])


@responses.activate
def test_bill_list_retrieve_update_delete(client):
    responses.add(responses.GET, f"{BASE}/Bill/", json=OK)
    responses.add(responses.GET, f"{BASE}/Bill/1/", json=OK)
    responses.add(responses.PUT, f"{BASE}/Bill/1/", json=OK)
    responses.add(responses.DELETE, f"{BASE}/Bill/1/", json=OK)
    client.bill.list(offset=0, limit=10)
    client.bill.retrieve(1)
    client.bill.update(1, note="n")
    client.bill.delete(1)
    assert responses.calls[3].request.method == "DELETE"


@responses.activate
def test_bill_create_with_every_collection(client):
    responses.add(responses.POST, f"{BASE}/Bill/", json=OK)
    client.bill.create(
        currency="CHF",
        positions=[{"name": "P", "price": 100}],
        recipient={"email": "a@b.c"},
        reference="R",
        date="2026-08-03",
        due_after_days=30,
        note="n",
        terms="t",
        language="fr",
        send=False,
        complete=False,
        shipping_cost=0,
        discount={"amount": 10},
        cash_discounts=[{"days": 10, "percentage": 2}],
        reminders=[{"days": 7}],
        additional_recipients=["c@d.e"],
        attachments=[{"name": "f.pdf"}],
        bank_information={"iban": "CH00"},
        service_period={"start": "2026-08-01"},
        payout_descriptor="d",
        payment_methods=["twint"],
        psp=[44],
        design=1,
        extra={"k": "v"},
    )
    body = request_body(responses.calls[0])
    assert "cashDiscounts%5B0%5D%5Bdays%5D=10" in body
    assert "additionalRecipients%5B0%5D=c%40d.e" in body
    assert "attachments%5B0%5D%5Bname%5D=f.pdf" in body
    assert "reminders%5B0%5D%5Bdays%5D=7" in body
    # send=False must travel as 0, not be dropped — a dropped flag would mail a draft.
    assert "send=0" in body


@responses.activate
def test_payout_list_and_retrieve(client):
    responses.add(responses.GET, f"{BASE}/Payout/", json=OK)
    responses.add(responses.GET, f"{BASE}/Payout/abc/", json=OK)
    client.payout.list(offset=0, limit=5)
    client.payout.retrieve("abc")
    assert request_url(responses.calls[1]).startswith(f"{BASE}/Payout/abc/")


@responses.activate
def test_qr_code_retrieve_delete_and_scan_delete(client):
    responses.add(responses.GET, f"{BASE}/QrCode/1/", json=OK)
    responses.add(responses.DELETE, f"{BASE}/QrCode/1/", json=OK)
    responses.add(responses.DELETE, f"{BASE}/QrCodeScan/sess/", json=OK)
    client.qr_code.retrieve(1)
    client.qr_code.delete(1)
    client.qr_code.delete_scan("sess")
    assert request_url(responses.calls[2]).startswith(f"{BASE}/QrCodeScan/sess/")


@responses.activate
def test_design_list_retrieve_create_delete(client):
    responses.add(responses.GET, f"{BASE}/Design/", json=OK)
    responses.add(responses.GET, f"{BASE}/Design/1/", json=OK)
    responses.add(responses.POST, f"{BASE}/Design/", json=OK)
    responses.add(responses.DELETE, f"{BASE}/Design/1/", json=OK)
    client.design.list()
    client.design.retrieve(1)
    client.design.create(name="Brand", backgroundColor="#fff", fontSize=14)
    client.design.delete(1)
    assert "backgroundColor=%23fff" in request_body(responses.calls[2])


@responses.activate
def test_payment_method_retrieve(client):
    responses.add(
        responses.GET,
        f"{BASE}/PaymentMethod/twint/",
        json={"status": "success", "data": [{"id": "twint", "name": "TWINT"}]},
    )
    assert client.payment_method.retrieve("twint").id == "twint"


@responses.activate
def test_payment_method_list_without_filters(client):
    responses.add(responses.GET, f"{BASE}/PaymentMethod/", json=EMPTY)
    assert client.payment_method.list() == []


@responses.activate
def test_payment_method_list_with_payment_type_filter(client):
    responses.add(responses.GET, f"{BASE}/PaymentMethod/", json=EMPTY)
    client.payment_method.list(payment_type="one-time")
    assert request_params(responses.calls[0])["filterPaymentType"] == "one-time"


# ----------------------------------------------------------------------
# PaymentMethodInfo — the id/name trap and the per-PSP options
# ----------------------------------------------------------------------

TWINT_METHOD: dict[str, Any] = {
    "id": "twint",
    "name": "TWINT",
    "label": {"en": "TWINT", "de": "TWINT"},
    "logo": {"en": "https://media.payrexx.com/twint.svg"},
    "options_by_psp": {
        "44": {"mode": "prod", "payment_types": ["one-time", "subscription"], "currencies": ["CHF"]}
    },
}


def test_payment_method_id_is_the_pm_identifier_not_name():
    """`id` is what a `pm` filter needs; `name` is a human label."""
    method = PaymentMethodInfo.from_api(TWINT_METHOD)
    assert method.id == "twint"
    assert method.name == "TWINT"


def test_payment_method_label_and_logo_are_language_maps():
    method = PaymentMethodInfo.from_api(TWINT_METHOD)
    assert method.label_for("de") == "TWINT"
    assert method.label_for("it") == "TWINT"  # falls back to en
    assert method.logo_for() == "https://media.payrexx.com/twint.svg"
    assert method.logo_for("zz") == "https://media.payrexx.com/twint.svg"


def test_payment_method_currencies_and_types_per_psp():
    method = PaymentMethodInfo.from_api(TWINT_METHOD)
    assert method.currencies(44) == ("CHF",)
    assert method.payment_types("44") == ("one-time", "subscription")
    assert method.currencies(99) == ()
    assert method.payment_types(99) == ()


def test_payment_method_tolerates_a_flattened_label():
    method = PaymentMethodInfo.from_api({"id": "visa", "label": "Visa", "logo": "u"})
    assert method.label_for() == "Visa"
    assert method.logo_for() == "u"


def test_payment_method_label_falls_back_to_name_then_default():
    bare = PaymentMethodInfo.from_api({"id": "x", "name": "X"})
    assert bare.label_for() == "X"
    nameless = PaymentMethodInfo.from_api({"id": "x"})
    assert nameless.label_for(default="fallback") == "fallback"


# ----------------------------------------------------------------------
# Signature check + auth token
# ----------------------------------------------------------------------


@responses.activate
def test_auth_token_create_sends_user_id(client):
    responses.add(responses.POST, f"{BASE}/AuthToken/", json=OK)
    client.auth_token.create(user_id=7)
    assert "userId=7" in request_body(responses.calls[0])


# ----------------------------------------------------------------------
# Model parsing edge cases
# ----------------------------------------------------------------------


def test_models_tolerate_empty_payloads():
    """Every model must survive a payload it did not expect.

    A parse error inside a webhook handler would turn a delivered payment into a
    retried one, so tolerance here is a correctness property, not politeness.
    """
    for model in (
        Transaction,
        Subscription,
        Invoice,
        Page,
        Bill,
        Payout,
        QrCode,
        Design,
        PaymentMethodInfo,
        AuthToken,
        EcrPayment,
    ):
        instance = model.from_api({})
        assert instance is not None


def test_transaction_refundable_amount_is_none_without_an_amount():
    assert Transaction.from_api({}).refundable_amount is None


def test_subscription_is_active_false_when_absent():
    assert Subscription.from_api({}).is_active is False


def test_bill_reads_both_camel_and_snake_case_keys():
    """Payrexx is inconsistent across endpoints, so both spellings are accepted."""
    camel = Bill.from_api({"paymentStatus": "paid", "paymentLink": "https://a"})
    snake = Bill.from_api({"payment_status": "paid", "payment_link": "https://a"})
    assert camel.payment_status == snake.payment_status == "paid"
    assert camel.payment_link == snake.payment_link == "https://a"


def test_invoice_and_page_parse_created_at():
    assert Invoice.from_api({"createdAt": 1786454809}).created_at is not None
    assert Page.from_api({"createdAt": 1786454809}).created_at is not None
    assert Invoice.from_api({}).created_at is None


def test_payout_defaults_are_safe():
    payout = Payout.from_api({})
    assert payout.transfers == ()
    assert payout.destination == {}
    assert payout.is_manual_payout is False
