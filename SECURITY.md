# Security policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.** This library handles
payment credentials, so a public report exposes every user of it before a fix
exists.

Report privately through
[GitHub Security Advisories](https://github.com/neoserviceai/payrexx-python/security/advisories/new).
You will get an acknowledgement within a few working days.

If the issue is in the **Payrexx API itself** rather than in this library, it
belongs to Payrexx: `integration@payrexx.com`. We are not affiliated with them and
cannot fix or coordinate on their side.

## Scope

In scope: credential handling, signature verification, request construction,
anything that could cause a wrong amount to be charged, a payment to be
misattributed, or a webhook to be accepted without a valid signature.

Out of scope: behaviour of the Payrexx API, the security of your own Payrexx
account, and the absence of features (see the README's Scope section).

## What this library does with credentials

- Keys are held in memory on the client instance and sent only as the
  `X-API-KEY` header to `api.payrexx.com` over HTTPS.
- `PayrexxClient.__repr__` never renders them, so they do not leak into logs or
  tracebacks that print the client.
- Nothing is written to disk, and nothing is logged at any level.
- Webhook signatures are compared with `hmac.compare_digest`, in constant time.

## Two things worth knowing as a user

**Payrexx API keys are not scoped.** An account can hold several keys and the back
office labels them by purpose — one may be marked *POS*. Verified against a live
account: a key labelled for a POS device reads the merchant API and the account
balance. Treat a key deployed on a terminal exactly like your main key.

**Nothing in the Payrexx API is idempotent.** This library never retries `POST`,
`PUT` or `PATCH` for that reason, and raises `PayrexxTransportError` — distinct
from a rejection — when a request produced no HTTP response. Do not retry a
terminal payment on that error: reconcile instead. Retrying can charge a customer
twice.
