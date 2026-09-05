"""DNS-Backend für die Hetzner Cloud API.

Spricht die API ausschließlich über hcloud-python an. Authentifizierung,
Paginierung und Wiederholungen übernimmt die Bibliothek.

Hetzner arbeitet aktionsorientiert: Eine Änderung an einem bestehenden RRSet
läuft über getrennte Endpunkte für RDATA und TTL. Ein RRSet, dessen Werte und
TTL sich beide ändern, kostet deshalb zwei Aufrufe. Ein Sammelaufruf über
mehrere RRSets existiert nicht, also ist die Anwendung nicht atomar.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import hcloud
from hcloud import Client
from hcloud.zones.domain import ZoneRecord

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

_ERROR_MAP = {
    'unauthorized': BackendAuthError,
    'forbidden': BackendPermissionError,
    'not_found': BackendNotFoundError,
    'rate_limit_exceeded': BackendRateLimitError,
    'invalid_input': BackendValidationError,
    'protected': BackendPermissionError,
}


def _wrap(e: Exception) -> BackendError:
    """Übersetzt eine hcloud-Ausnahme in die Backend-Fehlerhierarchie."""
    if isinstance(e, hcloud.APIException):
        code = str(getattr(e, 'code', '') or '')
        cls = _ERROR_MAP.get(code, BackendError)
        return cls(str(e))
    if isinstance(e, hcloud.HCloudException):
        return BackendUnavailableError(str(e))
    return BackendUnavailableError(str(e))


class HetznerBackend(DNSBackend):
    """Hetzner Cloud DNS."""

    name: ClassVar[str] = 'hetzner'
    default_api_base: ClassVar[str] = 'https://api.hetzner.cloud/v1'
    capabilities: ClassVar[BackendCapabilities] = BackendCapabilities(
        min_ttl=60,
        max_ttl=None,
        readonly_rdtypes=frozenset({'SOA'}),
        supports_zone_create=True,
        supports_zonefile_export=True,
        supports_zonefile_import=True,
        supports_zonefile_import_on_create=True,
        supports_protection=True,
        atomic_apply=False,
    )

    def __init__(self, token: str, api_base: str = '',
                 options: Mapping[str, Any] | None = None) -> None:
        super().__init__(token, api_base, options)
        self.client = Client(token=self.token, api_endpoint=self.api_base)

    # ------------------------------------------------------------------
    # Zonen
    # ------------------------------------------------------------------

    def list_zones(self) -> dict[str, Zone]:
        try:
            return {
                z.name: Zone(name=z.name, zone_id=str(z.id), native=z)
                for z in self.client.zones.get_all()
            }
        except (hcloud.HCloudException, OSError) as e:
            raise _wrap(e) from e

    def create_zone(self, domain: str) -> Zone:
        try:
            response = self.client.zones.create(name=domain, mode='primary')
        except (hcloud.HCloudException, OSError) as e:
            raise _wrap(e) from e
        zone = response.zone
        return Zone(name=zone.name, zone_id=str(zone.id), native=zone)

    def export_zonefile(self, zone: Zone) -> str:
        try:
            return self.client.zones.export_zonefile(zone.native).zonefile
        except (hcloud.HCloudException, OSError) as e:
            raise _wrap(e) from e

    def import_zonefile(self, zone: Zone, zonefile: str) -> None:
        """Ersetzt alle RRSets der Zone durch den Inhalt des Zonefiles."""
        try:
            self.client.zones.import_zonefile(zone.native, zonefile)
        except (hcloud.HCloudException, OSError) as e:
            raise _wrap(e) from e

    # ------------------------------------------------------------------
    # RRSets
    # ------------------------------------------------------------------

    def list_rrsets(self, zone: Zone) -> list[RRSet]:
        readonly = self.capabilities.readonly_rdtypes
        try:
            native_rrsets = self.client.zones.get_rrset_all(zone.native)
        except (hcloud.HCloudException, OSError) as e:
            raise _wrap(e) from e

        rrsets: list[RRSet] = []
        for r in native_rrsets:
            if r.type in readonly:
                continue
            values = tuple(sorted(
                self.canonicalize_rdata(r.type, rec.value) for rec in (r.records or [])
            ))
            rrsets.append(RRSet(
                name=r.name,
                rdtype=r.type,
                ttl=r.ttl,
                records=values,
                protected=bool(r.protection and r.protection.get('change')),
                handle=r,
            ))
        return rrsets

    def apply_changes(self, zone: Zone,
                      changes: Sequence[RRSetChange]) -> ApplyResult:
        """Setzt den Plan in Einzelaktionen um.

        Hetzner kennt keinen Sammelaufruf: Schlägt eine Änderung fehl, sind die
        vorherigen bereits wirksam. Fehlgeschlagene Löschungen brechen den Lauf
        nicht ab, sondern landen in ``ApplyResult.skipped``.
        """
        result = ApplyResult(atomic=False)

        for change in changes:
            try:
                if change.action == 'create':
                    self.client.zones.create_rrset(
                        zone.native, name=change.name, type=change.rdtype,
                        ttl=change.ttl,
                        records=[ZoneRecord(value=v) for v in change.records],
                    )
                elif change.action == 'update':
                    native = change.current.handle if change.current else None
                    self.client.zones.set_rrset_records(
                        native, [ZoneRecord(value=v) for v in change.records]
                    )
                    if change.current_ttl != change.ttl:
                        self.client.zones.change_rrset_ttl(native, change.ttl)
                elif change.action == 'delete':
                    native = change.current.handle if change.current else None
                    try:
                        self.client.zones.delete_rrset(native)
                    except hcloud.APIException as e:
                        # Eine nicht löschbare RRSet bricht den Lauf nicht ab.
                        logger.warning('RRSet %s/%s konnte nicht gelöscht werden: %s',
                                       change.name, change.rdtype, e)
                        result.skipped.append((change, str(e)))
                        continue
                else:
                    continue
            except (hcloud.HCloudException, OSError) as e:
                raise _wrap(e) from e
            result.applied += 1

        return result
