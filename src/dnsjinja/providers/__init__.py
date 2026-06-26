"""DNS-Provider-Abstraktion und Plugin-System (Tickets #9/#10)."""
from .base import (
    DnsProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderTransientError,
    RRSet,
    Zone,
)
from .pool import ProviderPool
from .registry import available_plugins, load_provider

__all__ = [
    "DnsProvider",
    "Zone",
    "RRSet",
    "ProviderError",
    "ProviderAuthError",
    "ProviderNotFoundError",
    "ProviderTransientError",
    "ProviderPool",
    "load_provider",
    "available_plugins",
]
