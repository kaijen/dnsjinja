"""Provider-neutrale Schnittstelle für DNS-Provider (Ticket #9).

`DNSJinja` programmiert ausschließlich gegen die hier definierten Typen und
die abstrakte Basis `DnsProvider`. Konkrete Provider (Hetzner, deSEC, …)
liegen als Plugins in eigenen Modulen und werden über die Registry geladen.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Provider-neutrale Datentypen
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    """Eine DNS-Zone bei einem Provider.

    `handle` kapselt das provider-eigene Objekt opak; der Kern reicht es nur
    durch und interpretiert es nicht.
    """
    name: str
    id: Any
    handle: Any = None


@dataclass
class RRSet:
    """Ein Resource-Record-Set provider-neutral.

    `name` ist der relative Owner-Name inkl. ``@`` für den Zonen-Apex.
    `records` sind die RDATA-Werte in Presentation-Form (FQDN mit Punkt).
    `handle` kapselt das provider-eigene RRSet-Objekt für spätere
    Update-/Delete-Operationen.
    """
    name: str
    type: str
    ttl: int
    records: list[str] = field(default_factory=list)
    protected: bool = False
    handle: Any = None


# ---------------------------------------------------------------------------
# Provider-neutrale Fehlerhierarchie
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Basisfehler für alle Provider-Operationen.

    Konkrete Plugins mappen ihre nativen Fehler (z. B. ``hcloud.APIException``)
    auf diese Hierarchie; der Kern fängt ausschließlich ``ProviderError``.
    """


class ProviderAuthError(ProviderError):
    """Authentifizierung/Autorisierung fehlgeschlagen (401/403, fehlendes Token)."""


class ProviderNotFoundError(ProviderError):
    """Angeforderte Ressource existiert nicht (404)."""


class ProviderTransientError(ProviderError):
    """Vorübergehender Fehler (Netz, 5xx, Rate-Limit) – ein Retry kann helfen."""


# ---------------------------------------------------------------------------
# Abstrakte Provider-Schnittstelle
# ---------------------------------------------------------------------------

class DnsProvider(ABC):
    """Provider-neutrale DNS-Operationen.

    Die gesamte Diff-/Sync-Logik (Vergleich Soll/Ist, create/update/delete,
    Protection-Behandlung) liegt im Kern (`DNSJinja`). Ein Plugin liefert nur
    die unten stehenden Primitive.
    """

    #: Kurzkennung des Plugins (z. B. "hetzner"), von der Registry gesetzt.
    name: str = "base"

    #: Ob der Provider DNSSEC-Signierung unterstützt (Ticket #11).
    supports_dnssec: bool = False

    # -- Zonen -------------------------------------------------------------

    @abstractmethod
    def list_zones(self) -> dict[str, Zone]:
        """Alle beim Provider vorhandenen Zonen als ``{name: Zone}``."""

    @abstractmethod
    def create_zone(self, name: str) -> Zone:
        """Eine neue Zone anlegen und zurückgeben."""

    # -- RRSets ------------------------------------------------------------

    @abstractmethod
    def get_rrsets(self, zone: Zone) -> list[RRSet]:
        """Alle RRSets einer Zone (SOA/Signatur-Records darf der Provider
        weglassen; der Kern filtert zusätzlich)."""

    @abstractmethod
    def create_rrset(self, zone: Zone, name: str, type: str, ttl: int,
                     records: list[str]) -> None:
        """Ein neues RRSet anlegen."""

    @abstractmethod
    def set_rrset_records(self, zone: Zone, rrset: RRSet,
                          records: list[str]) -> None:
        """Die RDATA-Werte eines bestehenden RRSets ersetzen."""

    @abstractmethod
    def set_rrset_ttl(self, zone: Zone, rrset: RRSet, ttl: int) -> None:
        """Den TTL eines bestehenden RRSets ändern."""

    @abstractmethod
    def delete_rrset(self, zone: Zone, rrset: RRSet) -> None:
        """Ein RRSet löschen."""

    # -- Optionales --------------------------------------------------------

    def supports_zonefile_export(self) -> bool:
        """Ob ``export_zonefile`` unterstützt wird (für Backups)."""
        return True

    def export_zonefile(self, zone: Zone) -> str:
        """Die Zone als BIND-Zonefile-Text exportieren."""
        raise NotImplementedError(
            f"Provider {self.name!r} unterstützt keinen Zonefile-Export")

    def close(self) -> None:
        """Optionale Ressourcenfreigabe."""
