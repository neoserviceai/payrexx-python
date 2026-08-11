# Getting started

## Install

```bash
pip install git+https://github.com/neoserviceai/payrexx-python.git
```

Python 3.10 or newer, and `requests`.

## Credentials

Three values, all from the merchant back office.

| Value | Where it lives |
|---|---|
| `instance` | the `<instance>` in `https://<instance>.payrexx.com` |
| `api_secret` | *API & Plugins* → the key of an active integration |
| webhook signing key | *Webhooks* — only needed to verify deliveries |

!!! danger "API keys are not scoped"
    An account can hold several keys, and the back office labels them by purpose —
    one may be marked *POS*. Verified against a live account: a key labelled for a
    POS device reads the merchant API **and the account balance**. Treat a key
    deployed on a terminal exactly like the main one.

!!! note "Plan requirement"
    The API is not available on the free plan — *API & Plugins* is greyed out there.
    The Standard plan or the 30-day trial is required.

## Build a client

```python
from payrexx import PayrexxClient

client = PayrexxClient(
    instance="my-shop",
    api_secret="…",
    pos_api_secret="…",  # optional; falls back to api_secret
    timeout=30.0,
    max_retries=2,  # idempotent verbs only — see the traps page
)
```

It works as a context manager, which closes the underlying session:

```python
with PayrexxClient(instance="my-shop", api_secret="…") as client:
    print(client.health_check())
```

`instance` is required and validated at construction. That is deliberate: every
Payrexx endpoint needs it, and its absence surfaces as an opaque `422` — better to
fail here than mid-payment.

## Check the credentials

```python
client.signature_check.check()  # True / False, never raises on a bad key

client.health_check()
# {'ok': True, 'instance': 'my-shop', 'providers': ['Payrexx Pay'],
#  'active_payment_methods': ['mastercard', 'twint', 'visa', …]}
```

`health_check` never raises — it returns `{"ok": False, "error": …}` on failure, so
it can back a monitoring endpoint directly.

## Amounts are always in the smallest currency unit

`1500` means CHF 15.00. This holds everywhere in the REST API and in this library.

!!! warning "The Tap to Pay SDK differs"
    Payrexx's Android Tap to Pay SDK takes **floats** (`25.00f`), not cents. If you
    bridge the two, convert in exactly one place and test it — a factor-of-100 error
    on a payment only shows up in production.

## Which payment methods can you actually offer?

```python
if "twint" in client.payment_provider.active_payment_methods():
    ...
```

A method can be *supported* by the PSP yet *disabled* on the account. Offering a
disabled one makes the hosted page reject the shopper's choice, so read the live
list rather than assuming.

For richer detail — labels per language, logos, and what each PSP accepts:

```python
for method in client.payment_method.list():
    print(method.id, method.label_for("fr"), method.currencies(44))
```

!!! tip "`id`, not `name`"
    `method.id` is `"mastercard"` — the identifier a `pm` filter needs.
    `method.name` is `"Mastercard"`, a human label. Passing the label into a filter
    gives you a filter Payrexx silently ignores.
