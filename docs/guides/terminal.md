# POS terminal (ECR)

Payrexx presents the ECR API as one interface across hardware vendors — you
integrate once and they translate to each terminal's own protocol. In practice only
the **NexGo N5, N6 and N86** are supported today.

!!! warning "No simulator"
    Unlike Stripe Terminal, Payrexx documents no ECR sandbox. Nothing on this page
    is exercisable without physical hardware, so the terminal is on the critical
    path of any integration.

## Pair a terminal

The pairing code comes from the device: hamburger menu (☰, top left) →
*Connect to cash register*. It is a six-character code such as `QP3U58`.

!!! danger "The code is short-lived"
    It **regenerates if you leave that screen** before pairing completes. Read it and
    call `pair` immediately.

```python
client.ecr.pair("SN-N86-1", "QP3U58", cashier_name="Till 1")
```

## Read the terminal's own configuration

```python
pairing = client.ecr.get_pairing("SN-N86-1")

print(pairing.currency)  # "CHF"
print(pairing.language)  # "fr"
print(pairing.point_of_sale_name)  # "Boutique"
print(pairing.timezone)  # "Europe/Zurich"
print(pairing.has_tipping)  # True
```

Reading these off the device beats hard-coding an assumption per client — and
`has_tipping` is worth checking before you send `tip_amount`, since a terminal with
tipping off may reject or drop it.

!!! note "A `404` does not prove the serial is wrong"
    `TerminalNotFoundError` is what Payrexx returns for an unknown serial *and* for
    a terminal that simply is not paired with this account.

## Take a payment

```python
payment = client.ecr.create_payment(
    "SN-N86-1",
    amount=1500,
    currency="CHF",
    payment_method="twint",  # omit to let the terminal show its chooser
    payment_reference="ORDER-1001",  # always set this
    purpose="Table 4",
    print_slip=True,
    tip_amount=100,
    shop_items=[
        client.ecr.shop_item("Beer", 500, quantity=2, vat=81),
        client.ecr.shop_item("Crisps", 350),
    ],
)

store(payment.payment_id)  # persist immediately — it addresses everything below
```

`payment_reference` is the only thread linking this terminal payment back to your
order once the webhook arrives. Always set it.

!!! danger "Never retry this call blindly"
    It is not idempotent. A request that times out may well have reached the
    terminal, and resending it can charge the customer twice. On
    `PayrexxTransportError`, treat the outcome as **unknown** and reconcile:

    ```python
    from payrexx.errors import PayrexxTransportError

    try:
        payment = client.ecr.create_payment(sn, amount=1500, currency="CHF", payment_reference=ref)
    except PayrexxTransportError:
        for tx in client.transaction.find_by_reference(ref):
            ...  # decide from what actually landed
    ```

## Follow the state

```python
state = client.ecr.get_payment("SN-N86-1", payment.payment_id)
print(state.status)  # a raw string — see the warning below
print(state.slip)  # receipt lines
```

!!! warning "`payment_status` is not enumerated"
    Payrexx's OpenAPI declares it as a bare string and lists no values, so
    `EcrPayment.status` is returned untouched. Do not compare it against guessed
    constants. For state you can rely on, use the transaction webhook
    (`type == "POS-Terminal"`), whose statuses **are** documented — and treat this
    field as a hint for the till UI.

## Cancel, void, refund

```python
client.ecr.cancel_payment("SN-N86-1", payment_id)  # still in progress
client.ecr.void_payment("SN-N86-1", payment_id)  # completed, pre-settlement
```

A void is all-or-nothing and generally only possible on the same day. For a partial
return, or once settled, refunds are **not available over ECR on NexGo devices** —
go through the merchant API instead:

```python
client.transaction.refund(transaction_id, amount=500)
```

Which of the three applies depends on the age of the transaction, so a till that
offers "return an item" needs to choose between them rather than always calling one.

!!! note "The payment id goes in the path"
    The REST reference shows `POST /ecr/{sn}/payment/cancel` with the id in the body.
    The official PHP SDK builds `/ecr/{sn}/payment/{id}/cancel`, and this library
    follows the SDK — both spellings return the same error against an unpaired
    terminal, so they could not be told apart without hardware.

## Which methods does this terminal accept?

```python
print(client.ecr.payment_methods("SN-N86-1"))
```

Sent as a `GET`, per the SDK. The reference says `POST`; both are routed.
