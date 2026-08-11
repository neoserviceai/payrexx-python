# The four traps

Four API behaviours that return `200 OK`, or an error naming the wrong thing. All
four are handled inside the library; they are documented here because they bite
anyone writing against the raw API — and because knowing them explains why parts of
this library look the way they do.

## 1. `instance` is required on every endpoint

Including `/ecr/*`, where the documentation never mentions it.

```
GET /v1.16/PaymentProvider/                    → 422 Unprocessable Content
GET /v1.16/PaymentProvider/?instance=my-shop   → 200 OK
```

The `422` carries an empty `reason` and a message that does not name the missing
parameter, so it reads like a malformed body.

**Handled by:** the client appends `instance` to every request and refuses to be
constructed without one — failing at construction beats failing mid-payment.

## 2. List filters need PHP's indexed brackets

Payrexx's own SDKs are PHP and post their payloads through `http_build_query`, so
the API only understands PHP's bracket notation.

| Sent | HTTP | `pm` echoed back | Hosted page shows |
|---|---|---|---|
| `pm=twint` | `200` | `[]` | **every method** |
| `pm[]=twint` | `200` | `[]` | **every method** |
| `pm[0]=twint` | `200` | `['twint']` | TWINT only |

Nothing signals that the filter was dropped. Verified against a live account on
2026-08-03, and confirmed on screen: with `pm[]=twint` the page offers all eight
methods, with `pm[0]=twint` it offers one.

**Why it matters:** the shopper has usually chosen a payment method upstream. A
filter that vanishes lets them pay by something else, and the payment no longer
matches what you recorded — which breaks reconciliation, not just the UI.

**Handled by:** every payload goes through
[`encode_form`][payrexx.encoding.encode_form], which reproduces
`http_build_query` — lists become `pm[0]`, mappings become
`fields[forename][value]`, booleans become `1`/`0`, and `None` is omitted rather
than sent as an empty string. `Gateway.filter_was_applied` lets you assert Payrexx
kept the filter, and a live test guards the encoding against regression.

## 3. Nothing is idempotent

There is no idempotency header, and `referenceId` correlates without enforcing
uniqueness. Two identical `POST /Gateway/` calls, same `referenceId`, same amount:

```
1st → 200, gateway id 36085493
2nd → 200, gateway id 36085494
```

Two independent gateways. Observed live.

**Handled by:** `POST`, `PUT` and `PATCH` are **never** retried; only `GET`, `HEAD`
and `DELETE` are, and only on a transport error or a `5xx`. A request that produced
no HTTP response raises `PayrexxTransportError`, a type distinct from a rejection,
because the two demand opposite responses:

```python
from payrexx.errors import PayrexxTransportError

try:
    payment = client.ecr.create_payment(sn, amount=1500, currency="CHF", payment_reference=ref)
except PayrexxTransportError:
    # The outcome is UNKNOWN — the terminal may already have charged the card.
    # Reconcile; never resend.
    for tx in client.transaction.find_by_reference(ref):
        ...
```

A rejection means nothing was charged. A transport error means you do not know.

On a gateway a duplicate costs an unused payment link. On a terminal it is a
**second charge**.

## 4. Webhook signatures have three sharp edges

`X-Webhook-Signature` is an HMAC-SHA256 that must be computed:

1. over the **raw request body** — never a re-serialised dict
2. with the signing key as **plain UTF-8 text** — not base64-decoded
3. rendered as **lowercase hexadecimal** — not base64

Get any one wrong and the mismatch looks exactly like a bad key, which sends you
looking in the wrong place.

**Handled by:** [`verify_signature`][payrexx.webhook.verify_signature] does all
three and compares in constant time.
