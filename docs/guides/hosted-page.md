# Hosted payment page

The web-checkout path: create a gateway, send the shopper to its `link`, and let the
transaction webhook confirm the outcome.

## Create

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
    look_and_feel_profile="42",  # a Design id
    skip_result_page=True,
    validity=60,  # link expires after 60 minutes
)

store(gateway.id, gateway.hash)  # persist these — they find the payment again
redirect(gateway.link)
```

`reference_id` travels back on the gateway and on the transaction webhook, which
makes it the natural anchor to your order or invoice.

!!! danger "`reference_id` does not enforce uniqueness"
    Two identical calls create two independent gateways. Call `create` once per
    order and persist the returned `id` and `hash`; to recover after a crash, use
    `find_by_reference` rather than creating a second gateway. See
    [The four traps](../traps.md#3-nothing-is-idempotent).

## Read it back

```python
gateway = client.gateway.retrieve(stored_id)
print(gateway.status)  # TransactionStatus.WAITING → …CONFIRMED
print(gateway.is_paid)
```

## Restrict the payment methods

```python
gateway = client.gateway.create(amount=500, currency="CHF", payment_methods=["twint"])
assert gateway.filter_was_applied  # Payrexx kept the filter
```

The library encodes `payment_methods` as `pm[0]`, `pm[1]`, … because that is the
only form Payrexx honours. `filter_was_applied` reads the filter back off the
response, which is the only way to know it took effect — a malformed filter returns
`200 OK` and is dropped in silence. See
[trap 2](../traps.md#2-list-filters-need-phps-indexed-brackets).

## Pre-authorise now, charge later

```python
gateway = client.gateway.create(amount=10000, currency="CHF", pre_authorization=True)
# … shopper pays, webhook arrives with status "authorized" …
client.transaction.capture(transaction_id, amount=8500)  # capture less if needed
```

An authorisation that is never captured ends up `uncaptured` and the hold lapses.

## Recurring payments

```python
gateway = client.gateway.create(
    amount=2900,
    currency="CHF",
    subscription_state=True,
    subscription_interval="P1M",  # ISO 8601 duration
    subscription_period="P1Y",
    subscription_cancellation_interval="P1M",
)
```

`payrexx.enums.Interval` carries the usual durations. Manage the resulting
agreement through `client.subscription`.

## Style it

```python
design = client.design.create(
    name="Brand", backgroundColor="#ffffff", buttonColor="#0b6e99", fontSize=14
)
gateway = client.gateway.create(amount=1000, currency="CHF", look_and_feel_profile=str(design.id))
```

Around thirty style keys are accepted and passed through as given — see
`DesignResource.create`.

!!! note "`Design` updates are a `POST`"
    Every other model updates with a `PUT`. The PHP SDK special-cases `Design`, and
    so does this library.
