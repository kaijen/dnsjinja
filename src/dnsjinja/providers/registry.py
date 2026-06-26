"""Plugin-Discovery für DNS-Provider (Ticket #9).

Auflösung einer Plugin-Kennung auf eine `DnsProvider`-Klasse, in dieser
Reihenfolge:

1. Expliziter Import-Pfad ``"paket.modul:Klasse"`` (Override/Fallback).
2. Entry-Point der Gruppe ``dnsjinja.providers`` (externe Plugin-Pakete).
3. Eingebaute Plugins (`_BUILTIN`) – damit der mitgelieferte Hetzner-Provider
   auch ohne (Neu-)Installation der Entry-Points funktioniert.
"""
from __future__ import annotations

import importlib
from importlib import metadata

from .base import DnsProvider, ProviderError

ENTRY_POINT_GROUP = "dnsjinja.providers"

#: Mitgelieferte Plugins als Fallback zu den Entry-Points.
_BUILTIN: dict[str, str] = {
    "hetzner": "dnsjinja.providers.hetzner:HetznerProvider",
}


def _load_path(path: str) -> type[DnsProvider]:
    module_name, _, attr = path.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def _entry_points() -> dict[str, metadata.EntryPoint]:
    try:
        eps = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:
        return {}
    return {ep.name: ep for ep in eps}


def available_plugins() -> list[str]:
    """Namen aller auflösbaren Plugins (Builtins + Entry-Points)."""
    return sorted(set(_BUILTIN) | set(_entry_points()))


def _resolve_class(plugin: str) -> type[DnsProvider]:
    if ":" in plugin:
        return _load_path(plugin)

    eps = _entry_points()
    if plugin in eps:
        return eps[plugin].load()

    if plugin in _BUILTIN:
        return _load_path(_BUILTIN[plugin])

    raise ProviderError(
        f"Unbekanntes Provider-Plugin {plugin!r}. "
        f"Verfügbar: {', '.join(available_plugins()) or '(keine)'}"
    )


def load_provider(plugin: str, *, token: str, api_base: str | None = None,
                  options: dict | None = None) -> DnsProvider:
    """Plugin laden und eine Provider-Instanz erzeugen."""
    cls = _resolve_class(plugin)
    provider = cls(token=token, api_base=api_base, options=options or {})
    # Kennung am Objekt sicherstellen (Plugins setzen i. d. R. `name`).
    if not getattr(provider, "name", None) or provider.name == "base":
        provider.name = plugin
    return provider
