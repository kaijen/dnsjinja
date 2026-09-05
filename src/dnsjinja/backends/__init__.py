"""DNS-Backends: die Anbieterschicht von dnsjinja.

Der Kern kennt nur die Typen aus :mod:`dnsjinja.backends.base`. Welches Backend
benutzt wird, entscheidet ``global.dns-backend`` in der config.json; aufgelöst
wird der Name in :mod:`dnsjinja.backends.registry`.
"""

from .base import (
    ApplyResult,
    BackendAuthError,
    BackendCapabilities,
    BackendError,
    BackendNotFoundError,
    BackendPermissionError,
    BackendRateLimitError,
    BackendUnavailableError,
    BackendValidationError,
    DNSBackend,
    RRKey,
    RRSet,
    RRSetChange,
    Zone,
)
from .registry import (
    ENTRY_POINT_GROUP,
    UnknownBackendError,
    available_backends,
    create_backend,
    get_backend_class,
)

__all__ = [
    'ApplyResult',
    'BackendAuthError',
    'BackendCapabilities',
    'BackendError',
    'BackendNotFoundError',
    'BackendPermissionError',
    'BackendRateLimitError',
    'BackendUnavailableError',
    'BackendValidationError',
    'DNSBackend',
    'RRKey',
    'RRSet',
    'RRSetChange',
    'Zone',
    'ENTRY_POINT_GROUP',
    'UnknownBackendError',
    'available_backends',
    'create_backend',
    'get_backend_class',
]
