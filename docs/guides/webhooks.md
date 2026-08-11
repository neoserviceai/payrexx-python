# Webhooks

Payrexx fires a webhook on every transaction or subscription status change, and it
covers **all three channels** — the payload's `type` is `E-Commerce`,
`POS-Terminal` or `Tap to Pay`. One endpoint is therefore enough to drive web,
terminal and Tap to Pay state.

Prefer this to polling: the rate limit is roughly **600 requests per 5 minutes** per
account, enforced by a WAF that answers `405` and then `403` if you keep going.

## Configure it

In the merchant back office, under *Webhooks*:

- **Endpoint** — your URL
- **Content type** — JSON or form-encoded; this library parses both
- **Retries** — enable them

Delivery is retried up to **10 times over 24 hours**: the first attempt within about
a minute, then 15 min, 1 h, 2 h, 4 h, then five daily attempts. Your endpoint must
answer within **20 seconds**.

## Handle it

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
        escalate_to_human(tx)  # not a refund

    return "ok"  # answer within 20 s or Payrexx keeps retrying
```

Answer `200` quickly and do the work asynchronously. An endpoint that does its
processing inline and exceeds 20 seconds turns one delivery into ten.

## Pass the raw body

```python
raw = request.get_data()  # Flask
raw = request.body  # Django
raw = frappe.request.get_data()  # Frappe
```

Never a re-serialised dict. Round-tripping through `json.loads`/`json.dumps` changes
the bytes without changing the meaning, and the signature no longer matches.

## Signature verification

`X-Webhook-Signature` is an HMAC-SHA256 with three details that are each easy to get
wrong, and each produces a mismatch that looks like a bad key:

1. the HMAC is over the **raw request body**
2. the signing key is used as **plain UTF-8 text**, not base64-decoded
3. the digest is **lowercase hexadecimal**, not base64

`verify_signature` does all three, comparing with `hmac.compare_digest`.

```python
from payrexx import verify_signature

if not verify_signature(raw_body, headers.get("X-Webhook-Signature"), KEY):
    return "invalid signature", 400
```

`parse_webhook` raises `WebhookSignatureError` on a mismatch by default. You can
pass `require_signature=False` to inspect a delivery while developing — but an
unverified webhook is attacker-controlled input and must never drive a payment state
machine.

## De-duplicating deliveries

Payrexx sends no event id, so `WebhookEvent.event_id` derives one:

```
payrexx_{transaction.uuid}_{transaction.status}
```

Stable across the ten delivery retries — same uuid, same status, same id — while
still distinguishing genuine state changes on the same transaction.

The residual risk is a legitimate re-emission of an identical status, which this
would swallow as a duplicate. That is the right trade: swallowing a redundant event
is harmless, whereas processing a retry twice is not.

## Routing on the channel

```python
match event.channel:
    case TransactionType.ECOMMERCE:
        ...
    case TransactionType.POS_TERMINAL:
        ...  # tx.pos_serial_number tells you which till
    case TransactionType.TAP_TO_PAY:
        ...
```

Tap to Pay transactions arrive here even though the Tap to Pay integration itself is
an Android SDK outside this library's scope.

## Disputes are not refunds

```python
if tx.is_disputed:  # chargeback or disputed
    escalate_to_human(tx)
```

Neither maps onto `refunded`, and treating them as one misstates the books. The same
caution applies to `insecure`: the money may have moved while the 3-D Secure
liability shift did not, so it warrants a look rather than an automatic success.
