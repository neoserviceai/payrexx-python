# payrexx-python

A Python client for the [Payrexx](https://payrexx.com) payment API — hosted payment
pages, transactions, subscriptions, QR bills, payouts, POS terminals (ECR) and
webhooks.

Payrexx ships official SDKs for [PHP](https://github.com/payrexx/payrexx-php),
[Node](https://github.com/payrexx/payrexx-node) and
[C#](https://github.com/payrexx/payrexx-c-sharp), but none for Python.

Coverage here is modelled on the **PHP SDK**, which documents more of the API than
the REST reference does. Behaviour is verified against a **live account**, not
inferred — see [What the docs omit](undocumented.md) for the seven findings that
came out of that, and [The four traps](traps.md) for the behaviours that fail
*silently* against a naive client.

```python
from payrexx import PayrexxClient

client = PayrexxClient(instance="my-shop", api_secret="…")

gateway = client.gateway.create(
    amount=1500,  # CHF 15.00 — always the smallest currency unit
    currency="CHF",
    reference_id="ORDER-1001",
    payment_methods=["twint"],
)
print(gateway.link)  # send the shopper here
```

## Install

```bash
pip install git+https://github.com/neoserviceai/payrexx-python.git
```

Python 3.10 or newer, and `requests`. No other dependencies and nothing tied to a
web framework.

## Coverage

| Namespace | Endpoint | What it does |
|---|---|---|
| `client.gateway` | `/Gateway/` | Hosted payment page, all 35 request fields |
| `client.transaction` | `/Transaction/` | Read, refund, capture, charge, pre-authorise, receipt, cancel, server-side filters |
| `client.subscription` | `/Subscription/` | Recurring payments |
| `client.invoice` | `/Invoice/` | Reusable payment link |
| `client.page` | `/Page/` | Hosted mini shop |
| `client.bill` | `/Bill/` | QR bill and purchase on invoice |
| `client.payout` | `/Payout/` | Payouts, with per-transfer detail |
| `client.qr_code` | `/QrCode/` | Static QR codes and scan sessions |
| `client.design` | `/Design/` | Look-and-feel profiles |
| `client.payment_method` | `/PaymentMethod/` | Labels, logos, per-PSP options |
| `client.payment_provider` | `/PaymentProvider/` | Which PSPs and methods are live |
| `client.signature_check` | `/SignatureCheck/` | Cheapest credential probe |
| `client.auth_token` | `/AuthToken/` | Back-office access tokens |
| `client.ecr` | `/ecr/{serial}/*` | POS terminals — NexGo N5, N6, N86 |
| `parse_webhook` | — | Signature verification, parsing, derived event id |

## Out of scope

**Tap to Pay**, permanently: it is not a REST API but an Android app-to-app
integration over Intents, so it lives in
[Payrexx's Android SDK](https://github.com/payrexx/TapToPaySDK). Tap to Pay
transactions do arrive through the webhook as `type == "Tap to Pay"`, and this
library parses those.

Also not covered: the platform Service API for managing merchant accounts.

## Not affiliated with Payrexx

An independent client library. For API questions, contact `integration@payrexx.com`
or read the [official reference](https://developers.payrexx.com/reference/rest-api).
