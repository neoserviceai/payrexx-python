"""Resource namespaces, reachable as attributes of :class:`payrexx.PayrexxClient`."""

from payrexx.resources.ecr import EcrResource
from payrexx.resources.gateway import GatewayResource
from payrexx.resources.payment_provider import PaymentProviderResource
from payrexx.resources.transaction import TransactionResource

__all__ = [
    "EcrResource",
    "GatewayResource",
    "PaymentProviderResource",
    "TransactionResource",
]
