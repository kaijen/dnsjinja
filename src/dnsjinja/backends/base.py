"""Backendneutrale Datentypen und die abstrakte Basisklasse für DNS-Backends.

Ein Backend kapselt alles, was ein DNS-Anbieter eigen hat: Authentifizierung,
Adressierung von Zonen, die Form der RRSet-Daten und die Art, wie Änderungen
geschrieben werden. Der Kern von dnsjinja kennt nur die Typen aus diesem Modul.

Kanonische Form innerhalb von dnsjinja:

* Owner-Namen sind relativ zur Zone, der Apex heißt '@'.
* RDATA-Ziele sind absolut (FQDN mit abschließendem Punkt).
* Die Werte eines RRSets sind sortiert.

Jedes Backend rechnet an seiner Außengrenze in diese Form um und zurück.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

import dns.rdata
import dns.rdataclass
import dns.rdatatype

# (relativer Owner-Name inkl. '@', RR-Typ)
RRKey = tuple[str, str]

# Länge eines einzelnen character-string in einem TXT-Record (RFC 1035).
_TXT_CHUNK_SIZE = 255


class BackendError(Exception):
    """Basis für alle Fehler, die ein Backend nach außen geben darf."""


class BackendAuthError(BackendError):
    """Token fehlt, ist ungültig oder hat keine Berechtigung."""


class BackendPermissionError(BackendError):
    """Der Anbieter verweigert die Änderung an diesem Objekt."""


class BackendNotFoundError(BackendError):
    """Zone oder RRSet existiert beim Anbieter nicht."""


class BackendRateLimitError(BackendError):
    """Das Ratenlimit des Anbieters ist erschöpft."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BackendUnavailableError(BackendError):
    """Netzwerkfehler, Zeitüberschreitung oder Serverfehler."""


class BackendValidationError(BackendError):
    """Der Anbieter hat die übermittelten Daten abgelehnt."""


@dataclass(frozen=True)
class RRSet:
    """Ein RRSet in kanonischer dnsjinja-Form."""
    name: str                                 # relativ, '@' für den Apex
    rdtype: str
    ttl: int
    records: tuple[str, ...] = ()             # sortiert, Ziele als FQDN
    protected: bool = False                   # Anbieter verbietet Änderungen
    handle: Any = None                        # backend-natives Objekt (nur Live-Daten)

    @property
    def key(self) -> RRKey:
        return self.name, self.rdtype


@dataclass(frozen=True)
class Zone:
    """Eine Zone beim Anbieter."""
    name: str                                 # 'example.com', ohne abschließenden Punkt
    zone_id: str                              # Hetzner: numerische ID; deSEC: der Name
    min_ttl: int | None = None                # zonenspezifische Untergrenze, falls bekannt
    native: Any = None                        # backend-natives Objekt


@dataclass
class RRSetChange:
    """Eine geplante Änderung an einem RRSet (Ergebnis von _plan_zone_rrsets())."""
    action: str               # 'create' | 'update' | 'delete' | 'protected' | 'unchanged'
    name: str                 # relativer Owner-Name ('@' für den Apex)
    rdtype: str
    ttl: int | None = None            # gewünschte TTL (None bei 'delete')
    records: list[str] = field(default_factory=list)         # gewünschte RDATA
    current_ttl: int | None = None    # TTL beim Anbieter (None bei 'create')
    current_records: list[str] = field(default_factory=list)  # RDATA beim Anbieter
    current: RRSet | None = None      # bestehendes RRSet (None bei 'create')

    @property
    def ttl_only(self) -> bool:
        """True, wenn sich ausschließlich die TTL unterscheidet (RDATA identisch)."""
        return self.action == 'update' and self.records == self.current_records


@dataclass
class ApplyResult:
    """Ergebnis von DNSBackend.apply_changes()."""
    applied: int = 0
    skipped: list[tuple[RRSetChange, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    atomic: bool = False


@dataclass(frozen=True)
class BackendCapabilities:
    """Was ein Backend kann und wo seine Grenzen liegen."""
    min_ttl: int = 1
    max_ttl: int | None = None
    readonly_rdtypes: frozenset[str] = frozenset({'SOA'})
    supports_zone_create: bool = True
    supports_zonefile_export: bool = True
    supports_zonefile_import: bool = False           # in eine bestehende Zone
    supports_zonefile_import_on_create: bool = False
    supports_protection: bool = False
    atomic_apply: bool = False
    max_records_per_rrset: int | None = None


class DNSBackend(ABC):
    """Schnittstelle zwischen dnsjinja und einem DNS-Anbieter."""

    name: ClassVar[str] = ''
    default_api_base: ClassVar[str] = ''
    capabilities: ClassVar[BackendCapabilities] = BackendCapabilities()

    def __init__(self, token: str, api_base: str = '',
                 options: Mapping[str, Any] | None = None) -> None:
        self.token = token
        self.api_base = (api_base or self.default_api_base).rstrip('/')
        self.options: dict[str, Any] = dict(options or {})

    # ------------------------------------------------------------------
    # Zonen
    # ------------------------------------------------------------------

    @abstractmethod
    def list_zones(self) -> dict[str, Zone]:
        """Alle Zonen des Kontos als {domainname: Zone}."""

    @abstractmethod
    def create_zone(self, domain: str) -> Zone:
        """Legt eine Zone an und liefert sie zurück."""

    @abstractmethod
    def export_zonefile(self, zone: Zone) -> str:
        """Liefert die Zone als Zonefile-Text."""

    # ------------------------------------------------------------------
    # RRSets
    # ------------------------------------------------------------------

    @abstractmethod
    def list_rrsets(self, zone: Zone) -> list[RRSet]:
        """Alle schreibbaren RRSets der Zone in kanonischer Form.

        Paginierung ist aufgelöst, Namen sind relativ ('@' für den Apex),
        RDATA ist kanonisiert und sortiert, und alle Typen aus
        ``capabilities.readonly_rdtypes`` sind herausgefiltert.
        """

    @abstractmethod
    def apply_changes(self, zone: Zone,
                      changes: Sequence[RRSetChange]) -> ApplyResult:
        """Wendet den kompletten Änderungsplan an.

        Der einzige schreibende Einstiegspunkt. Übergeben werden nur
        Änderungen mit Aktion 'create', 'update' oder 'delete'. Wie daraus
        Requests werden – ein atomarer Sammelaufruf oder viele Einzelaufrufe –
        entscheidet das Backend.
        """

    # ------------------------------------------------------------------
    # Normalisierung (konkret, bei Bedarf überschreibbar)
    # ------------------------------------------------------------------

    def effective_min_ttl(self, zone: Zone) -> int:
        """Kleinste TTL, die dieses Backend für diese Zone akzeptiert."""
        return max(self.capabilities.min_ttl, zone.min_ttl or 0)

    def canonicalize_rdata(self, rdtype: str, value: str) -> str:
        """Bringt einen RDATA-Wert in eine vergleichbare Form.

        dnspython vereinheitlicht Groß-/Kleinschreibung, Whitespace und die
        Notation von Adressen. TXT-Werte werden zusätzlich in Segmente zu
        höchstens 255 Byte zerlegt, weil Anbieter das serverseitig tun und
        ein ungechunkter Sollwert sonst einen Unterschied erzeugt, der sich
        nie schließt.
        """
        if rdtype in ('TXT', 'SPF'):
            value = _chunk_txt(value)
        try:
            rdata = dns.rdata.from_text(
                dns.rdataclass.IN, dns.rdatatype.from_text(rdtype), value
            )
        except Exception:
            return value
        return rdata.to_text()

    def normalize_desired(
        self, zone: Zone, desired: Mapping[RRKey, tuple[int, list[str]]]
    ) -> tuple[dict[RRKey, RRSet], list[str]]:
        """Passt die gerenderten Soll-Daten an die Grenzen des Backends an.

        Liefert die normalisierten RRSets und die Warnungen, die dabei
        entstanden sind. Wird an genau einer Stelle aufgerufen – am Kopf von
        ``_plan_zone_rrsets()`` –, damit Anzeige und Upload dieselben Daten
        sehen.
        """
        min_ttl = self.effective_min_ttl(zone)
        max_ttl = self.capabilities.max_ttl
        readonly = self.capabilities.readonly_rdtypes

        result: dict[RRKey, RRSet] = {}
        warnings: list[str] = []

        for (name, rdtype), (ttl, records) in desired.items():
            if rdtype in readonly:
                warnings.append(
                    f'{name}/{rdtype} wird von {self.name} verwaltet und nicht hochgeladen'
                )
                continue

            effective_ttl = ttl
            if effective_ttl < min_ttl:
                warnings.append(
                    f'{name}/{rdtype}: TTL {ttl} liegt unter der Mindest-TTL von '
                    f'{self.name} und wird auf {min_ttl} angehoben'
                )
                effective_ttl = min_ttl
            elif max_ttl is not None and effective_ttl > max_ttl:
                warnings.append(
                    f'{name}/{rdtype}: TTL {ttl} überschreitet die Höchst-TTL von '
                    f'{self.name} und wird auf {max_ttl} gekappt'
                )
                effective_ttl = max_ttl

            values = tuple(sorted(
                self.canonicalize_rdata(rdtype, v) for v in records
            ))
            result[(name, rdtype)] = RRSet(
                name=name, rdtype=rdtype, ttl=effective_ttl, records=values
            )

        return result, warnings

    def close(self) -> None:
        """Gibt Ressourcen frei. Standardmäßig ein No-op."""


def _chunk_txt(value: str) -> str:
    """Zerlegt einen TXT-Wert in Segmente zu höchstens 255 Byte.

    Bereits gechunkte Werte (mehrere Zeichenketten in Anführungszeichen)
    bleiben unangetastet – sie werden zusammengeführt und neu zerlegt, damit
    dieselbe Nutzlast unabhängig von der Schreibweise dieselbe Form ergibt.
    """
    parts = _split_txt_strings(value)
    if parts is None:
        return value
    joined = ''.join(parts)
    raw = joined.encode('utf-8')
    if len(raw) <= _TXT_CHUNK_SIZE:
        return '"' + joined.replace('\\', '\\\\').replace('"', '\\"') + '"'

    chunks: list[str] = []
    for start in range(0, len(raw), _TXT_CHUNK_SIZE):
        chunk = raw[start:start + _TXT_CHUNK_SIZE].decode('utf-8', errors='replace')
        chunks.append('"' + chunk.replace('\\', '\\\\').replace('"', '\\"') + '"')
    return ' '.join(chunks)


def _split_txt_strings(value: str) -> list[str] | None:
    """Zerlegt einen TXT-RDATA-Text in seine Einzelzeichenketten.

    Gibt None zurück, wenn der Wert nicht in Anführungszeichen steht – dann
    bleibt er unverändert, damit nichts kaputtgeht, was wir nicht verstehen.
    """
    text = value.strip()
    if not text.startswith('"'):
        return None

    parts: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == '"':
            if in_string:
                parts.append(''.join(current))
                current = []
            in_string = not in_string
        elif in_string:
            current.append(char)
        elif not char.isspace():
            return None
    if in_string:
        return None
    return parts
