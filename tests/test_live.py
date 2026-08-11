"""Live tests against a real Payrexx account.

Excluded from the default run (see ``addopts`` in ``pyproject.toml``) and skipped
unless credentials are present in the environment:

.. code-block:: bash

    export PAYREXX_INSTANCE=my-shop
    export PAYREXX_API_SECRET=…
    export PAYREXX_POS_API_KEY=…          # optional
    export PAYREXX_ECR_SERIAL=SN-N86-1    # optional, enables the terminal tests
    pytest tests/test_live.py -v

These tests create gateways on the account but **never complete a payment**, so
no money moves. Point them at a test account all the same.
"""

import os

import pytest

from payrexx import PayrexxClient, TransactionStatus
from payrexx.errors import TerminalNotFoundError

INSTANCE = os.environ.get("PAYREXX_INSTANCE")
API_SECRET = os.environ.get("PAYREXX_API_SECRET")
POS_KEY = os.environ.get("PAYREXX_POS_API_KEY")
ECR_SERIAL = os.environ.get("PAYREXX_ECR_SERIAL")

pytestmark = pytest.mark.skipif(
    not (INSTANCE and API_SECRET),
    reason="set PAYREXX_INSTANCE and PAYREXX_API_SECRET to run live tests",
)


@pytest.fixture(scope="module")
def client():
    assert INSTANCE, "PAYREXX_INSTANCE must be set; see the module docstring"
    assert API_SECRET, "PAYREXX_API_SECRET must be set; see the module docstring"
    with PayrexxClient(instance=INSTANCE, api_secret=API_SECRET, pos_api_secret=POS_KEY) as c:
        yield c


@pytest.fixture(scope="module")
def created(client):
    """Gateways created during the run, deleted afterwards."""
    ids: list[int] = []
    yield ids
    for gateway_id in ids:
        try:
            client.gateway.delete(gateway_id)
        except Exception as exc:  # noqa: BLE001 - cleanup must never fail the run
            print(f"could not delete gateway {gateway_id}: {exc}")


def test_health_check(client):
    result = client.health_check()
    assert result["ok"] is True, result
    print(f"\n  instance          : {result['instance']}")
    print(f"  providers         : {result['providers']}")
    print(f"  active methods    : {result['active_payment_methods']}")


def test_payment_providers(client):
    providers = client.payment_provider.list()
    assert providers
    for p in providers:
        print(f"\n  {p.id:>4}  {p.name:<20} active={list(p.active_payment_methods)}")


def test_create_and_read_gateway(client, created):
    gw = client.gateway.create(
        amount=1500,
        currency="CHF",
        reference_id="LIVE-TEST-GATEWAY",
        purpose="payrexx-python live test",
        success_redirect_url="https://example.com/ok",
    )
    created.append(gw.id)

    assert gw.id
    assert gw.hash
    assert gw.link
    assert gw.status == TransactionStatus.WAITING
    assert gw.reference_id == "LIVE-TEST-GATEWAY"
    assert gw.amount == 1500
    assert INSTANCE is not None
    assert INSTANCE in gw.link
    print(f"\n  created gateway {gw.id} → {gw.link}")

    again = client.gateway.retrieve(gw.id)
    assert again.id == gw.id
    assert again.reference_id == gw.reference_id


def test_payment_method_filter_is_honoured(client, created):
    """Proves the indexed-bracket encoding actually reaches Payrexx.

    The whole point of :mod:`payrexx.encoding`: a wrongly-encoded ``pm`` comes back
    empty and the hosted page offers every method.
    """
    active = client.payment_provider.active_payment_methods()
    method = "twint" if "twint" in active else sorted(active)[0]

    gw = client.gateway.create(
        amount=500, currency="CHF", reference_id="LIVE-TEST-PM", payment_methods=[method]
    )
    created.append(gw.id)

    assert gw.filter_was_applied, (
        f"Payrexx dropped the pm filter — got {gw.payment_methods!r}. "
        "The encoding regressed to a non-indexed form."
    )
    assert method in gw.payment_methods
    print(f"\n  filter honoured: pm={list(gw.payment_methods)}")


def test_transactions_are_listable(client):
    transactions = client.transaction.list()
    print(f"\n  {len(transactions)} transaction(s) on the account")
    for tx in transactions[:5]:
        print(f"    {tx.id} {tx.status} {tx.amount} {tx.currency} type={tx.type}")


def test_unknown_terminal_raises_terminal_not_found(client):
    """Confirms the ECR endpoint is reachable and authenticated.

    A ``404 Terminal not found`` — rather than a 403 or a 422 — means the path and
    credentials are right and only the hardware is missing.
    """
    with pytest.raises(TerminalNotFoundError):
        client.ecr.get_pairing("DEFINITELY-NOT-A-REAL-SERIAL")


@pytest.mark.skipif(not ECR_SERIAL, reason="set PAYREXX_ECR_SERIAL for terminal tests")
def test_terminal_pairing_status(client):
    pairing = client.ecr.get_pairing(ECR_SERIAL)
    print(f"\n  terminal {ECR_SERIAL}: paired={pairing.paired} raw={pairing.raw!r}")


@pytest.mark.skipif(not ECR_SERIAL, reason="set PAYREXX_ECR_SERIAL for terminal tests")
def test_terminal_payment_methods(client):
    print(f"\n  terminal methods: {client.ecr.payment_methods(ECR_SERIAL)!r}")
