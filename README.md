# payrexx-python

[![CI](https://github.com/neoserviceai/payrexx-python/actions/workflows/ci.yml/badge.svg)](https://github.com/neoserviceai/payrexx-python/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-2a6db2.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Python client for the [Payrexx](https://payrexx.com) payment API — hosted payment
pages, transactions, subscriptions, QR bills, payouts, POS terminals (ECR) and
webhooks.

Payrexx publishes official SDKs for [PHP](https://github.com/payrexx/payrexx-php),
[Node](https://github.com/payrexx/payrexx-node) and
[C#](https://github.com/payrexx/payrexx-c-sharp), but none for Python.

Coverage is modelled on the **PHP SDK**, which turns out to document more of the
API than the REST reference does — whole resources, dozens of gateway fields,
three undocumented transaction statuses, and the fact that `cancel` is a `DELETE`
while every sibling action is a `POST`. Behaviour is verified against a **live
account**, not inferred. The four traps in [Traps this library
handles](#traps-this-library-handles) all fail *silently* against a naive client.

```python
from payrexx import PayrexxClient

client = PayrexxClient(instance="my-shop", api_secret="…")

gateway = client.gateway.create(
    amount=1500,  # CHF 15.00 — always the smallest currency unit
    currency="CHF",
    reference_id="ORDER-1001",
    payment_methods=["twint"],
    success_redirect_url="https://example.com/thanks",
)
print(gateway.link)  # send the shopper here
```

## Install

```bash
pip install git+https://github.com/neoserviceai/payrexx-python.git
```

Once released to PyPI:

```bash
pip install payrexx
```

Python 3.10+ and `requests`. No other dependencies, nothing tied to a web
framework.

## Credentials

| Value | Where |
|---|---|
| `instance` | the `<instance>` in `https://<instance>.payrexx.com` |
| `api_secret` | *API & Plugins* → the key of an active integration |
| webhook signing key | *Webhooks* — only needed to verify deliveries |

> [!WARNING]
> **API keys are not scoped.** An account can hold several, and the back office
> labels them by purpose (e.g. one marked *POS*). Verified against a live account:
> a key labelled for a POS device reads the merchant API and the **account
> balance**. Treat a key deployed on a terminal exactly like the main one.

> [!NOTE]
> The API is **not available on the free plan** — *API & Plugins* is greyed out
> there. The Standard plan or the 30-day trial is required.

## What is covered

| Namespace | Endpoint | Notes |
|---|---|---|
| `client.gateway` | `/Gateway/` | Hosted payment page. All 35 request fields. |
| `client.transaction` | `/Transaction/` | Read, refund, capture, charge, pre-authorise, receipt, cancel, server-side filters |
| `client.subscription` | `/Subscription/` | Recurring payments |
| `client.invoice` | `/Invoice/` | Reusable payment link |
| `client.page` | `/Page/` | Hosted mini shop |
| `client.bill` | `/Bill/` | QR bill / purchase on invoice — positions, reminders, attachments |
| `client.payout` | `/Payout/` | Payouts, with per-transfer detail (v1.16) |
| `client.qr_code` | `/QrCode/` | Static QR codes and scan sessions |
| `client.design` | `/Design/` | Look-and-feel profiles |
| `client.payment_method` | `/PaymentMethod/` | Labels, logos, per-PSP options |
| `client.payment_provider` | `/PaymentProvider/` | Which PSPs and methods are live |
| `client.signature_check` | `/SignatureCheck/` | Cheapest credential probe |
| `client.auth_token` | `/AuthToken/` | Back-office access tokens |
| `client.ecr` | `/ecr/{serial}/*` | POS terminals (NexGo N5/N6/N86) |
| `parse_webhook` | — | Signature verification, parsing, derived event id |

**Tap to Pay is out of scope** and always will be: it is not a REST API but an
Android app-to-app integration over Intents, so it lives in
[Payrexx's Android SDK](https://github.com/payrexx/TapToPaySDK). Tap to Pay
transactions do arrive through the webhook (`type == "Tap to Pay"`), and this
library parses those.

Not covered: the platform Service API for managing merchant accounts.

## Usage

### Hosted payment page

```python
gateway = client.gateway.create(
    amount=4990,
    currency="CHF",
    reference_id="INV-2026-0042",
    purpose="Invoice 2026-0042",
    payment_methods=["twint", "visa", "mastercard"],
    success_redirect_url="https://example.com/paid",
    failed_redirect_url="https://example.com/failed",
    fields={"forename": {"value": "Jean"}, "email": {"value": "jean@example.com"}},
    look_and_feel_profile="42",  # a Design id
    skip_result_page=True,
    validity=60,  # link expires after 60 minutes
)

store(gateway.id, gateway.hash)  # persist these — they find the payment again
print(client.gateway.retrieve(gateway.id).status)
```

### POS terminal (ECR)

Only NexGo N5, N6 and N86 are supported by Payrexx today.

```python
# Pair once. The code comes from the terminal: ☰ → "Connect to cash register".
# It is short-lived and regenerates if you leave that screen.
pairing = client.ecr.pair("SN-N86-1", "QP3U58", cashier_name="Till 1")

# The terminal reports its own configuration — read it instead of assuming.
pairing = client.ecr.get_pairing("SN-N86-1")
print(pairing.currency, pairing.language, pairing.has_tipping)

payment = client.ecr.create_payment(
    "SN-N86-1",
    amount=1500,
    currency="CHF",
    payment_method="twint",  # omit to let the terminal ask
    payment_reference="ORDER-1001",  # always set this
    purpose="Table 4",
    print_slip=True,
    shop_items=[client.ecr.shop_item("Beer", 500, quantity=2, vat=81)],
)

state = client.ecr.get_payment("SN-N86-1", payment.payment_id)
client.ecr.cancel_payment("SN-N86-1", payment.payment_id)  # still in progress
client.ecr.void_payment("SN-N86-1", payment.payment_id)  # done, pre-settlement
```

`EcrPayment.status` is a **raw string** on purpose: Payrexx's OpenAPI declares
`payment_status` without enumerating any value. For state you can rely on, use the
transaction webhook.

### Webhooks

One endpoint covers all three channels — the payload's `type` is `E-Commerce`,
`POS-Terminal` or `Tap to Pay`. This is also why you should not poll: the rate
limit is ~600 requests per 5 minutes.

```python
from payrexx import parse_webhook, TransactionStatus, TransactionType


def handle(raw_body: bytes, headers: dict[str, str]) -> str:
    event = parse_webhook(raw_body, headers=headers, signing_key=SIGNING_KEY)

    if already_processed(event.event_id):  # retries deliver up to 10 times
        return "ok"

    tx = event.transaction
    if tx and tx.status == TransactionStatus.CONFIRMED:
        if tx.channel == TransactionType.POS_TERMINAL:
            settle_till(tx.reference_id, serial=tx.pos_serial_number)
        else:
            settle_order(tx.reference_id)
    elif tx and tx.is_disputed:
        escalate_to_human(tx)  # chargeback / disputed is not a refund

    return "ok"  # answer within 20 s or Payrexx keeps retrying
```

Pass the **unmodified** body: `request.get_data()` in Flask, `request.body` in
Django, `frappe.request.get_data()` in Frappe. Never a re-serialised dict.

### Account capabilities

```python
client.health_check()
# {'ok': True, 'instance': 'my-shop', 'providers': ['Payrexx Pay'],
#  'active_payment_methods': ['bank-transfer', 'mastercard', 'twint', 'visa', …]}

client.signature_check.check()  # True / False, never raises on a bad key

for method in client.payment_method.list():
    print(method.id, method.label_for("fr"), method.currencies(44))
```

A method can be *supported* by the PSP yet *disabled* on the account. Read the live
list rather than assuming — offering a disabled method makes the hosted page reject
the shopper's choice.

## Traps this library handles

Four behaviours that return `200 OK`, or an error naming the wrong thing.

### 1. `instance` is required on every endpoint

Including `/ecr/*`, where the documentation never mentions it. Without it Payrexx
answers `422 Unprocessable Content` with an empty `reason` and a message that does
not name the missing parameter.

The client appends it to every request and refuses to be constructed without one.

### 2. List filters must use PHP's indexed brackets

Payrexx's own SDKs are PHP and post through `http_build_query`, so the API only
understands `pm[0]=twint`.

| Sent | HTTP | `pm` echoed back | Page shows |
|---|---|---|---|
| `pm=twint` | `200` | `[]` | **every method** |
| `pm[]=twint` | `200` | `[]` | **every method** |
| `pm[0]=twint` | `200` | `['twint']` | TWINT only |

Nothing signals that the filter was dropped. It matters because the shopper has
usually already chosen a method upstream: a filter that vanishes lets them pay by
something else, and the payment no longer matches what you recorded.

Everything goes through `encode_form`, and `Gateway.filter_was_applied` lets you
assert Payrexx kept it. A live test guards the encoding against regression.

### 3. Nothing is idempotent

No idempotency header, and `referenceId` correlates without enforcing uniqueness.
Two identical `POST /Gateway/` calls produce two independent gateways — observed
live.

So **`POST`, `PUT` and `PATCH` are never retried**; only `GET`/`HEAD`/`DELETE` are.
Transport failures raise `PayrexxTransportError`, a type distinct from a rejection,
because the two demand opposite responses:

```python
from payrexx.errors import PayrexxTransportError

try:
    payment = client.ecr.create_payment(sn, amount=1500, currency="CHF", payment_reference=ref)
except PayrexxTransportError:
    # The outcome is UNKNOWN — the terminal may well have charged the card.
    # Reconcile; never resend.
    for tx in client.transaction.find_by_reference(ref):
        ...
```

On a gateway a duplicate costs an unused payment link. On a terminal it is a
**second charge**.

### 4. Webhook signatures have three sharp edges

`X-Webhook-Signature` is an HMAC-SHA256 over the raw body, with the signing key as
**plain UTF-8 text** (not base64-decoded), rendered as **lowercase hex** (not
base64). Get any one wrong and it looks like a bad key.

`verify_signature` does all three correctly, comparing in constant time.

## Things the REST reference does not tell you

Read off the PHP SDK, and worth knowing before you write against the raw API.

| | |
|---|---|
| **`cancel` is a `DELETE`** | On `Transaction` and `Subscription`, while `refund`, `capture`, `charge`, `preAuthorize` and `receipt` are all `POST`. |
| **`update` is a `PUT`** | …except on `Design`, which is a `POST`. The SDK special-cases exactly that one. |
| **Three extra statuses** | `initiated`, `insecure`, `uncaptured` exist in the SDK constants and in no documentation. Conversely `chargeback` is documented but **absent** from the SDK — so both sources are incomplete, which is why `TransactionStatus.parse` never raises on an unknown value. |
| **ECR ids go in the path** | The reference shows `POST /ecr/{sn}/payment/cancel` with the id in the body; the SDK builds `/ecr/{sn}/payment/{id}/cancel`. |
| **`paymentMethods` is a `GET`** | The reference says `POST`. |
| **`PaymentMethod.id` ≠ `.name`** | `id` is `"mastercard"` (what a `pm` filter needs); `name` is `"Mastercard"`. `label` and `logo` are per-language maps, not strings. |
| **v1.15 matters** | That release introduced specific HTTP status codes for failures. Below it, error mapping is unreliable — this client pins **v1.16**, the highest the API serves (`v1.17` answers "Version not found"). The PHP SDK still tops out at 1.15. |

## Transaction statuses

`TransactionStatus` carries all sixteen, with `is_final` and `is_successful`.

`chargeback` and `disputed` deserve care: neither is a refund, and mapping them
onto one misstates the books. `Transaction.is_disputed` flags them for a human.
`insecure` likewise is not treated as success — the money may have moved while the
liability shift did not.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pre-commit install          # optional, mirrors the CI gates

pytest                      # 132 tests, no network, coverage floor at 90%
ruff format . && ruff check . && mypy
```

The toolchain is strict on purpose — this library moves money, and a suite that
silently collects less than you think is worse than none:

- `pytest`: `--strict-markers`, `--strict-config`, `xfail_strict`,
  `filterwarnings = ["error"]`, `--cov-fail-under=90`, doctests run as tests
- `ruff`: format enforced (`--check` in CI, not auto-fixed), ~20 lint rule
  families including `S` (security), `DTZ` (naive datetimes), `ANN`, `D`
- `mypy --strict` over `src/` **and** `tests/`, plus `warn_unreachable` and
  `ignore-without-code` — a bare `# type: ignore` is not accepted

Every disabled rule in `pyproject.toml` carries the reason it is disabled.

Live tests run against a real account and are excluded by default:

```bash
export PAYREXX_INSTANCE=my-shop PAYREXX_API_SECRET=…
pytest tests/test_live.py -v -s
```

They create gateways and delete them afterwards, and never complete a payment.
Point them at a test account regardless.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The endpoints still missing — the platform
Service API in particular — are the most useful place to help.

Found a security problem? Do not open a public issue; see
[SECURITY.md](SECURITY.md).

## Not affiliated with Payrexx

An independent client library. For API questions, contact
`integration@payrexx.com` or read the
[official reference](https://developers.payrexx.com/reference/rest-api).

## License

MIT — see [LICENSE](LICENSE).
