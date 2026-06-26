"""Provider-Pool für den Multiprovider-Betrieb (Ticket #10).

Hält pro **benannter** Provider-Konfiguration genau eine `DnsProvider`-
Instanz (lazy erzeugt und gecacht). Schlüssel ist der Konfig-Name, nicht der
Plugin-Typ – so sind z. B. zwei Hetzner-Accounts mit unterschiedlichen Tokens
nebeneinander möglich.
"""
from __future__ import annotations

import os
from typing import Callable

from . import registry
from .base import DnsProvider, ProviderAuthError, ProviderError


class ProviderPool:
    """Verwaltet benannte Provider-Definitionen und ihre Instanzen.

    `definitions` bildet einen Namen auf eine Definition ab::

        {"hetzner-main": {"plugin": "hetzner",
                          "api-base": "https://api.hetzner.cloud/v1",
                          "token-env": "DNSJINJA_TOKEN_HETZNER_MAIN"}}

    Fehlt ``token-env``, wird `default_token` (z. B. ``--auth-api-token``)
    verwendet – das deckt den Single-Provider-/Legacy-Fall ab.
    """

    def __init__(self, definitions: dict[str, dict], *, default_token: str = "",
                 loader: Callable[..., DnsProvider] | None = None) -> None:
        self._definitions = definitions
        self._default_token = default_token
        self._loader = loader
        self._instances: dict[str, DnsProvider] = {}

    @property
    def names(self) -> list[str]:
        return list(self._definitions.keys())

    def _resolve_token(self, name: str, defn: dict) -> str:
        token_env = defn.get("token-env") or defn.get("token_env")
        if token_env:
            token = os.environ.get(token_env, "")
            if not token:
                raise ProviderAuthError(
                    f"Provider {name!r}: Umgebungsvariable {token_env} ist nicht gesetzt.")
            return token
        if not self._default_token:
            raise ProviderAuthError(
                f"Provider {name!r}: kein API-Token (weder token-env noch --auth-api-token).")
        return self._default_token

    def get(self, name: str) -> DnsProvider:
        """Provider-Instanz für einen Konfig-Namen (lazy, gecacht)."""
        if name in self._instances:
            return self._instances[name]
        if name not in self._definitions:
            raise ProviderError(
                f"Unbekannter Provider {name!r}. "
                f"Konfiguriert: {', '.join(self._definitions) or '(keine)'}")
        defn = self._definitions[name]
        plugin = defn.get("plugin", "hetzner")
        api_base = defn.get("api-base") or defn.get("api_base")
        token = self._resolve_token(name, defn)
        load = self._loader or registry.load_provider
        provider = load(plugin, token=token, api_base=api_base, options=defn)
        self._instances[name] = provider
        return provider

    def close(self) -> None:
        for provider in self._instances.values():
            try:
                provider.close()
            except Exception:
                pass
        self._instances.clear()
