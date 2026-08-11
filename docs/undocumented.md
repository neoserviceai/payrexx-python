# What the docs omit

Seven findings from reading the official
[PHP SDK](https://github.com/payrexx/payrexx-php) against the REST reference. Each
is handled in this library; each is worth knowing before writing against the raw
API.

Where the two sources disagree, the SDK has so far been right.

## `cancel` is a `DELETE`

On `Transaction` and `Subscription` — while `refund`, `capture`, `charge`,
`preAuthorize` and `receipt` are all `POST`. Counter-intuitive enough to be a
guaranteed bug if you assume consistency.

Read off `Communicator::$methods` in the SDK.

## `update` is a `PUT`, except on `Design`

Every model updates with a `PUT`. `Design` updates with a `POST`. The SDK
special-cases that one model explicitly, and so does this library.

## Three statuses exist only in the SDK

`initiated`, `insecure` and `uncaptured` appear in the SDK's response-model
constants and in no documentation. Conversely `chargeback` is documented in the
webhook reference but is **absent** from the SDK.

Both sources are therefore incomplete — which is exactly why
`TransactionStatus.parse` returns an unrecognised value unchanged instead of
raising. A status Payrexx adds tomorrow must not crash a till.

`insecure` deserves care: 3-D Secure was unavailable or bypassed, so the money may
have moved while the liability shift did not. It is not treated as success.

## ECR ids go in the path

The reference shows `POST /ecr/{sn}/payment/cancel` with the id in the request body.
The SDK's `setPaymentId()` assigns `'payment/' + id` as the resource id, producing
`POST /ecr/{sn}/payment/{id}/cancel`.

Both forms return the same `404 Terminal not found` against an unpaired terminal, so
live probing could not separate them. This library follows the SDK.

## `paymentMethods` is a `GET`

The reference says `POST`. The SDK maps `getEcrPaymentMethods` to `GET`. Both are
routed by the API.

## `PaymentMethod.id` is the identifier, not `.name`

The live shape:

```json
{
  "id": "mastercard",
  "name": "Mastercard",
  "label": {"en": "Mastercard"},
  "logo": {"en": "https://media.payrexx.com/assets/cardIcons/card_mastercard.svg"},
  "options_by_psp": {
    "44": {"mode": "prod",
           "payment_types": ["one-time", "reservation", "authorization", "subscription"],
           "currencies": ["CHF"]}
  }
}
```

`id` is what a `pm` filter needs. `name` is a human label. `label` and `logo` are
**per-language maps**, not strings — which the SDK's response model types as plain
strings, so even it is not fully right here.

Passing `name` into a `pm` filter produces a filter Payrexx silently ignores, which
is [trap 2](traps.md#2-list-filters-need-phps-indexed-brackets) all over again.

`PaymentMethodInfo` exposes `label_for()`, `logo_for()`, `currencies(psp_id)` and
`payment_types(psp_id)` to make the shape usable.

## Version 1.15 matters more than it looks

That release **introduced specific HTTP status codes for failed requests**. Below it,
the error mapping any client performs is unreliable.

This library pins **v1.16**, the highest the API serves:

```
GET /v1.0/PaymentProvider/    → 200
GET /v1.15/PaymentProvider/   → 200
GET /v1.16/PaymentProvider/   → 200
GET /v1.17/PaymentProvider/   → 404 "Version not found."
```

v1.16 additionally resolves payout aggregates into their underlying transfers on
`GET /Payout/{uuid}/details`; before, a repeated payout attempt came back as a
single aggregate row with an empty transaction object.

The official PHP SDK still tops out at 1.15.
