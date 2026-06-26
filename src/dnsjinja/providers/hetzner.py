"""Hetzner-Cloud-DNS-Provider-Plugin (Ticket #9).

Kapselt die `hcloud`-SDK hinter der provider-neutralen `DnsProvider`-
Schnittstelle. `hcloud` wird nur importiert, wenn dieses Plugin geladen wird –
der Kern (`dnsjinja.dnsjinja`) bleibt frei von Hetzner-Abhängigkeiten.
"""
from __future__ import annotations

import hcloud
from hcloud import Client
from hcloud.zones.domain import ZoneRecord

from .base import (
    DnsProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderTransientError,
    RRSet,
    Zone,
)


def _translate(exc: Exception) -> ProviderError:
    """Native hcloud-/OS-Fehler auf die ProviderError-Hierarchie abbilden."""
    if isinstance(exc, hcloud.APIException):
        code = exc.code
        if code in (401, 403, "unauthorized", "forbidden"):
            return ProviderAuthError(str(exc))
        if code in (404, "not_found"):
            return ProviderNotFoundError(str(exc))
        return ProviderError(str(exc))
    if isinstance(exc, (hcloud.HCloudException, OSError)):
        return ProviderTransientError(str(exc))
    return ProviderError(str(exc))


class HetznerProvider(DnsProvider):

    name = "hetzner"
    supports_dnssec = False

    DEFAULT_API_BASE = "https://api.hetzner.cloud/v1"

    def __init__(self, *, token: str, api_base: str | None = None,
                 options: dict | None = None) -> None:
        if not token:
            raise ProviderAuthError("Kein API-Token für den Hetzner-Provider angegeben.")
        base = (api_base or self.DEFAULT_API_BASE).rstrip("/")
        self._client = Client(token=token, api_endpoint=base)

    # -- Zonen -------------------------------------------------------------

    def list_zones(self) -> dict[str, Zone]:
        try:
            return {
                z.name: Zone(name=z.name, id=z.id, handle=z)
                for z in self._client.zones.get_all()
            }
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e

    def create_zone(self, name: str) -> Zone:
        try:
            response = self._client.zones.create(name=name, mode="primary")
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e
        z = response.zone
        return Zone(name=z.name, id=z.id, handle=z)

    # -- RRSets ------------------------------------------------------------

    def get_rrsets(self, zone: Zone) -> list[RRSet]:
        try:
            rrsets = self._client.zones.get_rrset_all(zone.handle)
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e
        result: list[RRSet] = []
        for rr in rrsets:
            protected = bool(rr.protection and rr.protection.get("change"))
            result.append(RRSet(
                name=rr.name,
                type=rr.type,
                ttl=rr.ttl,
                records=sorted(r.value for r in (rr.records or [])),
                protected=protected,
                handle=rr,
            ))
        return result

    def create_rrset(self, zone: Zone, name: str, type: str, ttl: int,
                     records: list[str]) -> None:
        try:
            self._client.zones.create_rrset(
                zone.handle, name=name, type=type, ttl=ttl,
                records=[ZoneRecord(value=v) for v in records],
            )
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e

    def set_rrset_records(self, zone: Zone, rrset: RRSet,
                          records: list[str]) -> None:
        try:
            self._client.zones.set_rrset_records(
                rrset.handle, [ZoneRecord(value=v) for v in records],
            )
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e

    def set_rrset_ttl(self, zone: Zone, rrset: RRSet, ttl: int) -> None:
        try:
            self._client.zones.change_rrset_ttl(rrset.handle, ttl)
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e

    def delete_rrset(self, zone: Zone, rrset: RRSet) -> None:
        try:
            self._client.zones.delete_rrset(rrset.handle)
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e

    # -- Backup ------------------------------------------------------------

    def supports_zonefile_export(self) -> bool:
        return True

    def export_zonefile(self, zone: Zone) -> str:
        try:
            return self._client.zones.export_zonefile(zone.handle).zonefile
        except (hcloud.HCloudException, OSError) as e:
            raise _translate(e) from e
