# payrexx-python

Python client for the [Payrexx](https://payrexx.com) payment API — hosted payment
pages, transactions, POS terminals (ECR) and webhooks.

Payrexx publishes official SDKs for [PHP](https://github.com/payrexx/payrexx-php),
[Node](https://github.com/payrexx/payrexx-node) and
[C#](https://github.com/payrexx/payrexx-c-sharp), but none for Python. This library
fills that gap.

It also encodes several API behaviours that are easy to get wrong — each one
verified against a live account rather than inferred from the documentation. They
are described in [Traps this library handles](#traps-this-library-handles), because
every one of them fails *silently*.

```python
from payrexx import PayrexxClient

client = PayrexxClient(instance="my-shop", api_secret="…")

gateway = client.gateway.create(
    amount=1500,                    # CHF 15.00 — always the smallest currency unit
    currency="CHF",
    reference_id="ORDER-1001",
    payment_methods=["twint"],
    success_redirect_url="https://example.com/thanks",
)
print(gateway.link)                 # send the shopper here
```

## Install

```bash
pip install git+https://github.com/neoserviceai/payrexx-python.git
```

Requires Python 3.10+ and `requests`. No other dependencies, and nothing tied to a
particular web framework.

## Credentials

Two values, both from the merchant back office:

| Value | Where |
|---|---|
| `instance` | the `<instance>` in `https://<instance>.payrexx.com` |
| `api_secret` | *API & Plugins* → the key of an active integration |
| webhook signing key | *Webhooks* — only needed to verify deliveries |

An account can hold several keys, and the back office labels them by purpose
(e.g. one marked *POS*). **They are not scoped.** Any key grants full merchant
access, account balance included — verified by calling the merchant API with a
key labelled for a POS device. Treat a key deployed on a terminal exactly like the
main one.

> The API is **not available on the free plan**. *API & Plugins* is greyed out
> there; the Standard plan or the 30-day trial is required.

## Usage

### Hosted payment page (web checkout)

```python
gateway = client.gateway.create(
    amount=4990,
    currency="CHF",
    reference_id="INV-2026-0042",
    purpose="Invoice 2026-0042",
    payment_methods=["twint", "visa", "mastercard"],
    success_redirect_url="https://example.com/paid",
    failed_redirect_url="https://example.com/failed",
    cancel_redirect_url="https://example.com/cancelled",
    fields={"forename": {"value": "Jean"}, "email": {"value": "jean@example.com"}},
)

# Persist these two immediately — they are how you find the payment again.
store(gateway.id, gateway.hash)

later = client.gateway.retrieve(gateway.id)
print(later.status)                 # TransactionStatus.WAITING → …CONFIRMED
```

### POS terminal (ECR)

Only NexGo N5, N6 and N86 are supported by Payrexx today.

```python
# Pair once. The code comes from the terminal: ☰ → "Connect to cash register".
# It is short-lived and regenerates if you leave that screen.
client.ecr.pair("SN-N86-1", "QP3U58", cashier_name="Till 1")

payment = client.ecr.create_payment(
    "SN-N86-1",
    amount=1500,
    currency="CHF",
    payment_method="twint",            # omit to let the terminal ask
    payment_reference="ORDER-1001",    # always set this
    print_slip=True,
)

state = client.ecr.get_payment("SN-N86-1", payment.payment_id)
```

`EcrPayment.status` is returned as a **raw string** on purpose: Payrexx's OpenAPI
declares `payment_status` without enumerating any values. For state you can rely
on, use the transaction webhook — see below.

### Webhooks

One endpoint covers all three channels. The payload's `type` is `E-Commerce`,
`POS-Terminal` or `Tap to Pay`, so routing needs no separate URLs. This is also
why you should not poll: the rate limit is ~600 requests per 5 minutes.

```python
from payrexx import parse_webhook, TransactionStatus, TransactionType

def handle(raw_body: bytes, headers: dict[str, str]) -> str:
    event = parse_webhook(raw_body, headers=headers, signing_key=SIGNING_KEY)

    if already_processed(event.event_id):     # retries deliver up to 10 times
        return "ok"

    tx = event.transaction
    if tx and tx.status == TransactionStatus.CONFIRMED:
        if tx.channel == TransactionType.POS_TERMINAL:
            settle_till(tx.reference_id, serial=tx.pos_serial_number)
        else:
            settle_order(tx.reference_id)

    return "ok"      # answer within 20 s or Payrexx keeps retrying
```

Pass the **unmodified** request body. In Flask that is `request.get_data()`, in
Django `request.body`, in Frappe `frappe.request.get_data()` — never a
re-serialised dict.

### Account capabilities

```python
client.health_check()
# {'ok': True, 'instance': 'my-shop',
#  'providers': ['Payrexx Pay'],
#  'active_payment_methods': ['bank-transfer', 'mastercard', 'twint', 'visa', …]}

if "twint" in client.payment_provider.active_payment_methods():
    ...
```

A method can be *supported* by the PSP yet *disabled* on the account. Offering a
disabled one makes the hosted page reject the shopper's choice, so read the live
list rather than assuming.

## Traps this library handles

Four API behaviours that return `200 OK` — or an error that names the wrong thing —
and would otherwise bite in production.

### 1. `instance` is required on every endpoint

Including `/ecr/*`, where the documentation never mentions it. Without it Payrexx
answers `422 Unprocessable Content` with an empty `reason` and a message that does
not name the missing parameter.

The client appends it to every request, and refuses to be constructed without one.

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
assert that Payrexx kept the filter.

### 3. Nothing is idempotent

There is no idempotency header, and `referenceId` correlates without enforcing
uniqueness. Two identical `POST /Gateway/` calls produce two independent gateways —
observed live.

The client therefore **never retries a POST**, only `GET`/`HEAD`/`DELETE`.
Transport failures raise `PayrexxTransportError`, distinct from a rejection,
because the two demand opposite responses:

```python
from payrexx.errors import PayrexxTransportError

try:
    payment = client.ecr.create_payment(sn, amount=1500, currency="CHF",
                                        payment_reference=ref)
except PayrexxTransportError:
    # The outcome is UNKNOWN — the terminal may well have charged the card.
    # Reconcile; never resend.
    for tx in client.transaction.find_by_reference(ref):
        ...
```

On a gateway a duplicate costs an unused payment link. On a terminal it is a
**second charge**.

### 4. Webhook signatures have three sharp edges

`X-Webhook-Signature` is an HMAC-SHA256 that must be computed over the raw body,
with the signing key as **plain UTF-8 text** (not base64-decoded), rendered as
**lowercase hex** (not base64). Get any one wrong and it looks like a bad key.

`verify_signature` does it correctly, comparing in constant time.

## Transaction statuses

`TransactionStatus` covers all thirteen values, with `is_final` and `is_successful`
helpers.

`chargeback` and `disputed` deserve care: neither is a refund, and mapping them
onto one misstates the books. `Transaction.is_disputed` flags them so they can be
escalated to a human rather than folded into an automated transition.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

pytest                  # unit tests, no network
ruff check . && mypy     # lint + types
```

Unit tests stub HTTP with [`responses`](https://github.com/getsentry/responses) and
need no credentials. `tests/test_live.py` exercises a real account and is excluded
by default; it runs only when `PAYREXX_INSTANCE` and `PAYREXX_API_SECRET` are set:

```bash
pytest tests/test_live.py -v
```

It creates gateways on the account and never completes a payment. Point it at a
test account.

## Scope

Covered: hosted gateways, transactions (read, refund, capture), payment providers,
ECR terminals, webhook verification and parsing.

Not covered yet: subscriptions, payouts, invoices, paylinks, and the platform
Service API for managing merchant accounts. Contributions welcome.

**Tap to Pay is out of scope** and always will be — it is not a REST API but an
Android app-to-app integration over Intents, so it lives in
[Payrexx's Android SDK](https://github.com/payrexx/TapToPaySDK). Tap to Pay
transactions do arrive through the webhook (`type == "Tap to Pay"`), and this
library parses those.

## Not affiliated with Payrexx

An independent client library. For API questions, contact
`integration@payrexx.com` or read the
[official reference](https://developers.payrexx.com/reference/rest-api).

## License

MIT — see [LICENSE](LICENSE).
