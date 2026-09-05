"""In-Memory-Backend für Tests.

Erfüllt den DNSBackend-Vertrag, zeichnet alle Aufrufe auf und wendet
Änderungen tatsächlich auf den eigenen Zustand an. Nur so lässt sich prüfen,
dass ein zweiter Planungslauf nach einem Upload keine Unterschiede mehr findet.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from dnsjinja.backends import (
    ApplyResult,
    BackendCapabilities,
    BackendError,
    DNSBackend,
    RRSet,
    RRSetChange,
    Zone,
)


class FakeBackend(DNSBackend):
    """Backend ohne Netz, mit aufgezeichnetem Verhalten."""

    name: ClassVar[str] = 'fake'
    default_api_base: ClassVar[str] = 'https://fake.invalid/v1'
    capabilities: ClassVar[BackendCapabilities] = BackendCapabilities(
        min_ttl=60,
        max_ttl=None,
        readonly_rdtypes=frozenset({'SOA'}),
        supports_zone_create=True,
        supports_zonefile_export=True,
        supports_zonefile_import=True,
        supports_protection=True,
        atomic_apply=False,
    )

    def __init__(self, token: str = 'fake-token', api_base: str = '',
                 options: Mapping[str, Any] | None = None) -> None:
        super().__init__(token, api_base, options)
        self.zones: dict[str, Zone] = {}
        self.rrsets: dict[str, list[RRSet]] = {}
        self.zonefiles: dict[str, str] = {}

        # Aufzeichnung
        self.calls: list[tuple[str, Any]] = []
        self.created: list[str] = []
        self.applied: list[list[RRSetChange]] = []

        # Fehlerinjektion: Methodenname -> Exception, optional je Zone
        self.fail_on: dict[str, BackendError] = {}
        self.fail_on_zone: dict[tuple[str, str], BackendError] = {}

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    @classmethod
    def with_zones(cls, names: Sequence[str], **kwargs: Any) -> 'FakeBackend':
        backend = cls(**kwargs)
        for n in names:
            backend.add_zone(n)
        return backend

    def add_zone(self, name: str, **kwargs: Any) -> Zone:
        zone = Zone(name=name, zone_id=f'id-{name}', native=object(), **kwargs)
        self.zones[name] = zone
        self.rrsets.setdefault(name, [])
        self.zonefiles.setdefault(name, f'$ORIGIN {name}.\n$TTL 3600\n')
        return zone

    def _check(self, method: str, zone: Zone | None = None) -> None:
        if zone is not None and (method, zone.name) in self.fail_on_zone:
            raise self.fail_on_zone[(method, zone.name)]
        if method in self.fail_on:
            raise self.fail_on[method]

    # ------------------------------------------------------------------
    # Zonen
    # ------------------------------------------------------------------

    def list_zones(self) -> dict[str, Zone]:
        self.calls.append(('list_zones', None))
        self._check('list_zones')
        return dict(self.zones)

    def create_zone(self, domain: str) -> Zone:
        self.calls.append(('create_zone', domain))
        self._check('create_zone')
        self.created.append(domain)
        return self.add_zone(domain)

    def export_zonefile(self, zone: Zone) -> str:
        self.calls.append(('export_zonefile', zone))
        self._check('export_zonefile', zone)
        return self.zonefiles[zone.name]

    # ------------------------------------------------------------------
    # RRSets
    # ------------------------------------------------------------------

    def list_rrsets(self, zone: Zone) -> list[RRSet]:
        self.calls.append(('list_rrsets', zone))
        self._check('list_rrsets', zone)
        readonly = self.capabilities.readonly_rdtypes
        return [r for r in self.rrsets.get(zone.name, []) if r.rdtype not in readonly]

    def apply_changes(self, zone: Zone,
                      changes: Sequence[RRSetChange]) -> ApplyResult:
        self.calls.append(('apply_changes', zone))
        self._check('apply_changes', zone)
        self.applied.append(list(changes))

        result = ApplyResult(atomic=self.capabilities.atomic_apply)
        current = {r.key: r for r in self.rrsets.get(zone.name, [])}

        for change in changes:
            key = (change.name, change.rdtype)
            if change.action == 'delete':
                current.pop(key, None)
            else:
                current[key] = RRSet(
                    name=change.name, rdtype=change.rdtype, ttl=change.ttl or 0,
                    records=tuple(change.records),
                    protected=bool(change.current and change.current.protected),
                )
            result.applied += 1

        self.rrsets[zone.name] = list(current.values())
        return result
