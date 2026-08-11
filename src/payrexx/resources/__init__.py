"""Resource namespaces, reachable as attributes of :class:`payrexx.PayrexxClient`."""

from payrexx.resources.ecr import EcrResource
from payrexx.resources.gateway import GatewayResource
from payrexx.resources.misc import (
    AuthTokenResource,
    BillResource,
    DesignResource,
    InvoiceResource,
    PageResource,
    PaymentMethodResource,
    PayoutResource,
    QrCodeResource,
    SignatureCheckResource,
)
from payrexx.resources.payment_provider import PaymentProviderResource
from payrexx.resources.subscription import SubscriptionResource
from payrexx.resources.transaction import TransactionResource

__all__ = [
    "AuthTokenResource",
    "BillResource",
    "DesignResource",
    "EcrResource",
    "GatewayResource",
    "InvoiceResource",
    "PageResource",
    "PaymentMethodResource",
    "PaymentProviderResource",
    "PayoutResource",
    "QrCodeResource",
    "SignatureCheckResource",
    "SubscriptionResource",
    "TransactionResource",
]
