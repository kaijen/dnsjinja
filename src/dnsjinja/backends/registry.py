"""Auflösung von DNS-Backends über Name.

Eingebaute Backends stehen in ``_BUILTIN`` und werden erst beim Zugriff
importiert, damit ``hcloud`` bzw. ``requests`` nur geladen werden, wenn das
jeweilige Backend tatsächlich benutzt wird. Fremde Pakete tragen Backends über
die Entry-Point-Gruppe ``dnsjinja.backends`` bei.

Die config.json nennt ausschließlich Namen. Ein Modulpfad wird bewusst nicht
akzeptiert – sonst entschiede eine Konfigurationsdatei darüber, welcher Code
ausgeführt wird.
"""

import logging
from importlib import import_module
from importlib.metadata import entry_points
from typing import Any, Mapping

from .base import DNSBackend

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = 'dnsjinja.backends'

# Name -> 'modul:Klasse'
_BUILTIN: dict[str, str] = {
    'hetzner': 'dnsjinja.backends.hetzner:HetznerBackend',
    'desec': 'dnsjinja.backends.desec:DesecBackend',
}


class UnknownBackendError(Exception):
    """Der in der Konfiguration genannte Backend-Name ist nicht auflösbar."""


def _iter_entry_points():
    try:
        return list(entry_points(group=ENTRY_POINT_GROUP))
    except Exception as e:  # defektes Paket-Metadatum darf uns nicht anhalten
        logger.warning('Entry-Points der Gruppe %s konnten nicht gelesen werden: %s',
                       ENTRY_POINT_GROUP, e)
        return []


def available_backends() -> dict[str, str]:
    """Alle auflösbaren Backend-Namen und ihre Herkunft.

    Lädt nichts – gibt nur Namen aus. Eingebaute Backends gewinnen bei
    Namensgleichheit.
    """
    found: dict[str, str] = {}
    for ep in _iter_entry_points():
        if ep.name in _BUILTIN:
            # Die eigenen Backends sind absichtlich auch als Entry-Point
            # eingetragen; nur ein fremdes Paket unter demselben Namen ist
            # eine Meldung wert.
            if getattr(ep, 'value', '') != _BUILTIN[ep.name]:
                logger.warning(
                    'Entry-Point %r aus %s überschreibt kein eingebautes Backend '
                    'und wird ignoriert',
                    ep.name, getattr(ep, 'value', '?'),
                )
            continue
        found[ep.name] = getattr(getattr(ep, 'dist', None), 'name', None) or 'plugin'
    found.update({name: 'builtin' for name in _BUILTIN})
    return dict(sorted(found.items()))


def _load_builtin(name: str) -> type[DNSBackend]:
    module_path, _, class_name = _BUILTIN[name].partition(':')
    module = import_module(module_path)
    return getattr(module, class_name)


def get_backend_class(name: str) -> type[DNSBackend]:
    """Löst einen Backend-Namen zu seiner Klasse auf."""
    if name in _BUILTIN:
        return _load_builtin(name)

    for ep in _iter_entry_points():
        if ep.name != name:
            continue
        try:
            loaded = ep.load()
        except Exception as e:
            logger.warning('Backend-Plugin %r konnte nicht geladen werden: %s', name, e)
            continue
        if not (isinstance(loaded, type) and issubclass(loaded, DNSBackend)):
            logger.warning('Backend-Plugin %r ist keine DNSBackend-Klasse und wird ignoriert',
                           name)
            continue
        return loaded

    verfuegbar = ', '.join(available_backends())
    raise UnknownBackendError(
        f'Unbekanntes DNS-Backend {name!r}. Verfügbar: {verfuegbar}'
    )


def create_backend(name: str, token: str, api_base: str = '',
                   options: Mapping[str, Any] | None = None) -> DNSBackend:
    """Erzeugt eine Backend-Instanz zum konfigurierten Namen."""
    return get_backend_class(name)(token=token, api_base=api_base, options=options)
