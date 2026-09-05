"""DNS-Backend für die deSEC-API (https://desec.io).

Drei Eigenheiten prägen die Umsetzung:

* **Bulk statt Einzelaktionen.** Ein einziger PATCH auf
  ``/domains/{name}/rrsets/`` setzt alle RRSets der Zone – atomar, alles oder
  nichts. ``apply_changes()`` schickt deshalb genau einen Request, unabhängig
  davon, wie viele RRSets sich ändern. Gelöscht wird über ``"records": []``.
* **Der Apex hat zwei Schreibweisen.** In der URL eines Einzelzugriffs heißt er
  ``@``, im Bulk-Body dagegen der leere String. Beide Formen entstehen
  ausschließlich in ``_wire_subname()`` / ``_from_wire_subname()``, damit die
  Vergleichsschicht nie eine Wire-Form sieht.
* **Harte Ratenlimits.** 2/s, 15/min, 100/h und 300/Tag je Domain für
  Änderungen. Ein 429 kommt mit ``Retry-After``; das wird hier begrenzt
  wiederholt, statt den Lauf abzubrechen.

DNSSEC signiert deSEC selbst. SOA, DNSKEY, DS und die übrigen signaturnahen
Typen sind schreibgeschützt und werden auf beiden Seiten des Vergleichs
ausgefiltert – sonst plante dnsjinja für jeden davon eine Löschung.
"""

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import requests

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
    RRSet,
    RRSetChange,
    Zone,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
MAX_RETRY_WAIT = 60


class DesecBackend(DNSBackend):
    """deSEC DNS."""

    name: ClassVar[str] = 'desec'
    default_api_base: ClassVar[str] = 'https://desec.io/api/v1'
    capabilities: ClassVar[BackendCapabilities] = BackendCapabilities(
        min_ttl=3600,
        max_ttl=86400,
        readonly_rdtypes=frozenset({
            'SOA', 'DNSKEY', 'DS', 'CDS', 'CDNSKEY',
            'RRSIG', 'NSEC', 'NSEC3', 'NSEC3PARAM',
        }),
        supports_zone_create=True,
        supports_zonefile_export=True,
        supports_zonefile_import=False,           # nur beim Anlegen der Domain
        supports_zonefile_import_on_create=True,
        supports_protection=False,
        atomic_apply=True,
        max_records_per_rrset=4091,
    )

    def __init__(self, token: str, api_base: str = '',
                 options: Mapping[str, Any] | None = None) -> None:
        super().__init__(token, api_base, options)
        self.timeout = int(self.options.get('timeout', DEFAULT_TIMEOUT))
        self.max_retries = int(self.options.get('rate-limit-retries', DEFAULT_MAX_RETRIES))
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    def close(self) -> None:
        self.session.close()

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Setzt einen Request ab und übersetzt Fehler in BackendError.

        Bei 429 wird bis zu ``max_retries`` mal gewartet und wiederholt – die
        Ratenlimits von deSEC sind eng genug, dass ein Lauf über mehrere
        Domains sie regulär erreicht.
        """
        url = path if path.startswith('http') else f'{self.api_base}{path}'
        kwargs.setdefault('timeout', self.timeout)

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.RequestException as e:
                raise BackendUnavailableError(f'{method} {url}: {e}') from e

            if response.status_code != 429:
                break

            if attempt >= self.max_retries:
                raise BackendRateLimitError(
                    f'Ratenlimit von deSEC erschöpft: {_body(response)}',
                    retry_after=_retry_after(response),
                )
            wait = min(_retry_after(response) or 2 ** attempt, MAX_RETRY_WAIT)
            logger.warning('deSEC-Ratenlimit erreicht, warte %.1fs (Versuch %d/%d)',
                           wait, attempt + 1, self.max_retries)
            time.sleep(wait)

        _raise_for_status(response, method, url)
        return response

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        """Folgt der Cursor-Paginierung über den Link-Header.

        deSEC liefert bis zu 500 Einträge auf einmal; darüber hinaus verlangt
        es den Parameter ``cursor``.
        """
        items: list[dict[str, Any]] = []
        url: str | None = path
        while url:
            response = self._request('GET', url)
            items.extend(response.json())
            url = _next_link(response)
        return items

    # ------------------------------------------------------------------
    # Zonen
    # ------------------------------------------------------------------

    def list_zones(self) -> dict[str, Zone]:
        zones: dict[str, Zone] = {}
        for d in self._paginate('/domains/'):
            zones[d['name']] = _zone_from_json(d)
        return zones

    def create_zone(self, domain: str) -> Zone:
        response = self._request('POST', '/domains/', json={'name': domain})
        return _zone_from_json(response.json())

    def export_zonefile(self, zone: Zone) -> str:
        response = self._request(
            'GET', f'/domains/{zone.name}/zonefile/',
            headers={'Accept': 'text/dns'},
        )
        return response.text

    # ------------------------------------------------------------------
    # RRSets
    # ------------------------------------------------------------------

    def list_rrsets(self, zone: Zone) -> list[RRSet]:
        readonly = self.capabilities.readonly_rdtypes
        rrsets: list[RRSet] = []
        for r in self._paginate(f'/domains/{zone.name}/rrsets/'):
            rdtype = r['type']
            if rdtype in readonly:
                continue
            values = tuple(sorted(
                self.canonicalize_rdata(rdtype, v) for v in r.get('records', [])
            ))
            rrsets.append(RRSet(
                name=_from_wire_subname(r.get('subname', '')),
                rdtype=rdtype,
                ttl=int(r['ttl']),
                records=values,
                protected=False,
                handle=r,
            ))
        return rrsets

    def apply_changes(self, zone: Zone,
                      changes: Sequence[RRSetChange]) -> ApplyResult:
        """Schickt den kompletten Plan als einen atomaren Bulk-PATCH."""
        result = ApplyResult(atomic=True)
        payload = [self._change_to_payload(c) for c in changes
                   if c.action in ('create', 'update', 'delete')]
        if not payload:
            return result

        self._request('PATCH', f'/domains/{zone.name}/rrsets/', json=payload)
        result.applied = len(payload)
        return result

    def _change_to_payload(self, change: RRSetChange) -> dict[str, Any]:
        entry: dict[str, Any] = {
            'subname': _wire_subname(change.name),
            'type': change.rdtype,
            # Löschen heißt bei deSEC: RRSet mit leerer Werteliste schicken.
            'records': [] if change.action == 'delete' else list(change.records),
        }
        if change.action != 'delete':
            entry['ttl'] = change.ttl
        return entry


# ----------------------------------------------------------------------
# Wire-Form des Apex
# ----------------------------------------------------------------------

def _wire_subname(name: str) -> str:
    """Kanonischer Name -> subname im Bulk-Body ('@' wird zum leeren String)."""
    return '' if name == '@' else name


def _from_wire_subname(subname: str) -> str:
    """subname aus der API -> kanonischer Name (leerer String wird zu '@')."""
    return '@' if subname == '' else subname


# ----------------------------------------------------------------------
# HTTP-Hilfen
# ----------------------------------------------------------------------

def _body(response: requests.Response) -> str:
    try:
        return str(response.json())
    except ValueError:
        return response.text[:500]


def _retry_after(response: requests.Response) -> float | None:
    raw = response.headers.get('Retry-After')
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _next_link(response: requests.Response) -> str | None:
    """Liest die URL der nächsten Seite aus dem Link-Header."""
    for name, link in (response.links or {}).items():
        if name == 'next' and link.get('url'):
            return link['url']
    return None


def _raise_for_status(response: requests.Response, method: str, url: str) -> None:
    status = response.status_code
    if status < 400:
        return
    detail = _body(response)
    if status == 401:
        raise BackendAuthError(f'deSEC weist das Token zurück: {detail}')
    if status == 403:
        raise BackendPermissionError(f'deSEC verweigert {method} {url}: {detail}')
    if status == 404:
        raise BackendNotFoundError(f'deSEC kennt {url} nicht: {detail}')
    if status in (400, 422):
        raise BackendValidationError(f'deSEC lehnt die Daten ab: {detail}')
    if status >= 500:
        raise BackendUnavailableError(f'deSEC antwortet mit {status}: {detail}')
    raise BackendError(f'deSEC antwortet mit {status} auf {method} {url}: {detail}')


def _zone_from_json(data: Mapping[str, Any]) -> Zone:
    return Zone(
        name=data['name'],
        zone_id=data['name'],          # deSEC adressiert Domains über den Namen
        min_ttl=data.get('minimum_ttl'),
        native=dict(data),
    )
