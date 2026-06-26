---
id: 9
title: 'Provider-Abstraktion: DNS-API hinter Plugin-Schnittstelle entkoppeln'
status: backlog
priority: high
created: 2026-06-26T11:00:00+02:00
updated: 2026-06-26T11:00:00+02:00
tags:
    - refactoring
    - architecture
    - plugin
    - provider
    - hetzner
class: standard
---

## Ziel

Die konkrete DNS-Provider-API (aktuell fest Hetzner Cloud via `hcloud`) so
abstrahieren, dass `DNSJinja` nur noch gegen eine provider-neutrale
Schnittstelle programmiert. Konkrete Provider werden als **Plugins** geladen
und sind zur Laufzeit über Konfiguration austauschbar (z. B. Hetzner, INWX,
deSEC, PowerDNS, Cloudflare …), ohne den Kern zu ändern.

Rendering (Jinja2 + dnspython) bleibt provider-unabhängig und ist nicht
Gegenstand des Refactorings – nur der Teil "Zonen ermitteln/anlegen, RRSets
synchronisieren, Zonefile exportieren" wird hinter die Abstraktion gezogen.

## Motivation

`src/dnsjinja/dnsjinja.py` mischt zwei Verantwortlichkeiten:
1. **Provider-neutral**: Templates rendern, SOA-Serial bilden, Zonen-Syntax
   prüfen, gerenderte RRSets parsen, Zonefiles schreiben/backuppen.
2. **Hetzner-spezifisch**: `hcloud.Client`, `client.zones.*`, `ZoneRecord`,
   `hcloud.APIException`/`HCloudException`, `export_zonefile`, Hetzner-eigene
   `protection`-Semantik, API-Endpoint-Default.

Dadurch ist ein zweiter Provider heute nur per Fork/Hack möglich. Die
Provider-Logik ist außerdem schwer isoliert testbar (Offline-Tests müssen
`hcloud` mocken).

## Inventar der Hetzner-Kopplung (Stand heute)

Alles in `src/dnsjinja/dnsjinja.py`, sofern nicht anders genannt:

- Importe: `import hcloud`, `from hcloud import Client`,
  `from hcloud.zones.domain import ZoneRecord` (Z. 6–8)
- `DEFAULT_API_BASE = "https://api.hetzner.cloud/v1"` (Z. 43)
- `self.client = Client(token=..., api_endpoint=self._api_base)` (Z. 119)
- `self._hetzner_zones: dict[str, Any]` (Z. 120)
- `_prepare_zones()` (Z. 57–83): `client.zones.get_all()`,
  `client.zones.create(name=…, mode="primary")`, `hcloud.APIException`,
  `hcloud.HCloudException`
- `_sync_zone_rrsets()` (Z. 224–266): `client.zones.get_rrset_all()`,
  `ZoneRecord(value=…)`, `set_rrset_records()`, `change_rrset_ttl()`,
  `create_rrset()`, `delete_rrset()`, `rrset.protection['change']`,
  `hcloud.APIException`
- `backup_zone()` (Z. 287–295): `client.zones.export_zonefile()`,
  `hcloud.APIException`
- `upload_zone()` (Z. 268–275): `hcloud.APIException`
- Config-Schema `dns_api_base` Default + Pattern auf Hetzner-URL
  (`src/dnsjinja/dnsjinja_config_schema.py`, Z. 17–21)
- CLI-Texte/Docstrings nennen "Hetzner Cloud API" (`run()`-Docstring Z. 320,
  `--auth-api-token`-Hilfe Z. 317)
- Dependency `hcloud>=2.0` als harte Abhängigkeit in `pyproject.toml`

## Zielarchitektur

### 1. Provider-neutrale Schnittstelle

Neues Modul `src/dnsjinja/providers/base.py`:

- Datentypen (dataclasses, provider-neutral):
  - `Zone(name: str, id: str, handle: Any)` – `handle` kapselt das
    provider-eigene Objekt opak für den Kern.
  - `RRSet(name: str, type: str, ttl: int, records: list[str],
    protected: bool = False)`
- Abstrakte Basis `DnsProvider` (ABC oder `typing.Protocol`) mit
  provider-neutralen Operationen:
  - `name: str` (Plugin-Kennung, z. B. "hetzner")
  - `list_zones() -> dict[str, Zone]`
  - `create_zone(name: str) -> Zone`
  - `get_rrsets(zone: Zone) -> list[RRSet]`  (SOA wird vom Kern gefiltert)
  - `create_rrset(zone, name, type, ttl, records: list[str]) -> None`
  - `set_rrset_records(zone, rrset: RRSet, records: list[str]) -> None`
  - `set_rrset_ttl(zone, rrset: RRSet, ttl: int) -> None`
  - `delete_rrset(zone, rrset: RRSet) -> None`
  - `export_zonefile(zone: Zone) -> str`  (optional; `ProviderCapability`
    o. Ä. wenn ein Provider kein Zonefile-Export kann -> Backup-Skip mit
    klarer Meldung statt Crash)
  - `close() -> None` (optional, Ressourcenfreigabe)
- Provider-neutrale Exceptions in `base.py`:
  - `ProviderError(Exception)` – Basis
  - `ProviderAuthError`, `ProviderNotFoundError`, `ProviderTransientError`
  - Jeder Provider mappt seine nativen Fehler (z. B. `hcloud.APIException`)
    auf diese Typen. Der Kern fängt **nur** `ProviderError`-Subtypen.

Granularität bewusst auf RRSet-Operationen statt "apply(desired)": Die
gesamte Diff-/Sync-Logik (`_sync_zone_rrsets`, Protection-Check,
create/update/delete-Reihenfolge) bleibt provider-neutral im Kern und wird
NICHT in jedes Plugin dupliziert. Das Plugin liefert nur die CRUD-Primitive.

### 2. Plugin-Discovery

Zwei kombinierbare Mechanismen:

- **Entry Points** (bevorzugt, für externe Pakete): Gruppe
  `dnsjinja.providers` in `pyproject.toml`. Laden via
  `importlib.metadata.entry_points(group="dnsjinja.providers")`.
  Eingebauter Hetzner-Provider wird selbst als Entry Point registriert:

      [project.entry-points."dnsjinja.providers"]
      hetzner = "dnsjinja.providers.hetzner:HetznerProvider"

- **Direkter Import-Pfad** (Fallback/Override): Config-Wert
  `provider: "my_pkg.module:MyProvider"` erlaubt das Laden ohne Entry Point.

Eine `registry.py` mit `load_provider(name_or_path, *, token, api_base,
options) -> DnsProvider` löst Name -> Klasse auf, instanziiert und liefert
bei Unbekanntem eine klare Fehlermeldung inkl. Liste verfügbarer Provider.

### 3. Konfiguration & CLI

- Neuer optionaler Config-Key `global.provider` (Default: `"hetzner"` für
  Rückwärtskompatibilität).
- `global.provider-options` (offenes Objekt) für provider-spezifische
  Extras, ohne Schema-Änderungen am Kern.
- `dns-api-base` bleibt, aber das Hetzner-spezifische `^https://api.hetzner`
  wird gelockert (nur noch `^https://`, wie bereits) bzw. in
  Provider-Defaults verlagert; Default-Endpoint kommt künftig vom jeweiligen
  Provider, nicht aus dem Kern (`DEFAULT_API_BASE` entfernen).
- CLI: `--provider` (envvar `DNSJINJA_PROVIDER`) ergänzt; `--auth-api-token`
  bleibt, Hilfetexte generalisieren ("DNS-Provider-API" statt "Hetzner Cloud
  API"). `run()`-Docstring entschärfen.

### 4. Kern-Umbau (`dnsjinja.py`)

- `DNSJinja.__init__` ruft `load_provider(...)` und hält `self.provider`
  statt `self.client`. `self._hetzner_zones` -> `self._zones: dict[str, Zone]`.
- `_prepare_zones()` nutzt `provider.list_zones()` / `provider.create_zone()`
  und fängt `ProviderError`.
- `_sync_zone_rrsets()` arbeitet mit `RRSet`-Datentyp und ruft
  `provider.get_rrsets/create_rrset/set_rrset_records/set_rrset_ttl/
  delete_rrset`. `ZoneRecord` verschwindet aus dem Kern.
- `backup_zone()` nutzt `provider.export_zonefile()`.
- Hetzner-Importe komplett aus `dnsjinja.py` entfernt.

### 5. Hetzner-Plugin

`src/dnsjinja/providers/hetzner.py`: `HetznerProvider(DnsProvider)` kapselt
`hcloud.Client` und implementiert das Interface 1:1 zur heutigen Logik
(inkl. `protection['change']` -> `RRSet.protected`,
`mode="primary"` beim Anlegen, `export_zonefile`). `hcloud` wird damit zu
einer **optionalen** Abhängigkeit (`pyproject.toml` extras
`[providers-hetzner]`), die nur beim Laden des Plugins importiert wird – der
Kern bleibt importierbar ohne `hcloud`.

## Refactoring-Schritte (Reihenfolge)

1. `providers/base.py`: Datentypen + ABC + Exceptions (reiner Code, keine
   Verhaltensänderung).
2. `providers/registry.py`: Entry-Point-/Pfad-Discovery + `load_provider`.
3. `providers/hetzner.py`: bestehende Hetzner-Aufrufe 1:1 hinter das
   Interface ziehen; native Fehler auf `ProviderError` mappen.
4. `dnsjinja.py` auf `self.provider` umstellen, Hetzner-Importe entfernen.
5. Config-Schema + CLI: `provider`/`provider-options`/`--provider`,
   `DEFAULT_API_BASE` entfernen, Hilfetexte generalisieren.
6. `pyproject.toml`: Entry Point registrieren, `hcloud` in optionales Extra
   verschieben (Default-Install zieht Hetzner weiter mit -> kein Breaking
   Change für Bestandsnutzer; via `dependencies` einbinden, Extra nur für
   die Trennung dokumentieren).
7. Doku aktualisieren (`docs/hetzner-api.md` -> generisch + Hetzner als
   Beispiel; README-Abschnitt "Provider/Plugins"; `AGENT.md`).

## Tests

- **FakeProvider** (`tests/`): In-Memory-Implementierung des Interface.
  Damit werden Offline-Render-/Sync-Tests provider-unabhängig und brauchen
  kein `hcloud`-Mocking mehr. Deckt create/update/delete-Diff, TTL-Change,
  Protection-Skip, fehlende Zone, leere Zone ab.
- **Registry-Tests**: Auflösung per Entry-Point-Name, per Import-Pfad,
  unbekannter Provider -> klare Fehlermeldung.
- **Hetzner-Plugin-Tests**: Mapping nativer `hcloud.APIException` ->
  `ProviderError`; RRSet-Konvertierung (`ZoneRecord` <-> `RRSet`),
  Protection-Flag.
- **Regression**: bestehende `tests/test_unit.py` /
  `tests/test_config_cases.py` müssen grün bleiben (Rendering/Parsing
  unverändert). Integrationstests (Marker `integration`) laufen weiter gegen
  Hetzner-Testdomain.

## Rückwärtskompatibilität

- Ohne `provider`-Key verhält sich alles wie heute (Default Hetzner).
- Bestehende `config.json` und Templates bleiben unverändert gültig.
- Default-`pip install dnsjinja-kaijen` installiert weiterhin Hetzner-Support.

## Risiken / offene Punkte

- Provider mit unterschiedlicher Protection-/TTL-Semantik: Interface muss
  generisch genug sein, ohne Hetzner-Eigenheiten zu lecken.
- Provider ohne Zonefile-Export (`backup`) sauber als "nicht unterstützt"
  signalisieren statt Abbruch.
- `dns-api-base`-Pattern: heutige Validierung ist Hetzner-zentriert; pro
  Provider verlagern, ohne bestehende Configs zu brechen.
- API-Token-Modell: andere Provider brauchen ggf. mehrere Credentials ->
  über `provider-options` lösen, nicht über neue Top-Level-CLI-Flags.

## Akzeptanzkriterien

- [ ] `dnsjinja.py` importiert kein `hcloud` mehr; alle Provider-Aufrufe
      laufen über `self.provider` (DnsProvider-Interface).
- [ ] Ein zusätzlicher Provider kann allein durch ein Plugin-Paket
      (Entry Point) + `provider:`-Config eingebunden werden, ohne Änderung
      am Kern.
- [ ] FakeProvider-basierte Offline-Tests grün; kein `hcloud`-Mock mehr im
      Kern-Test nötig.
- [ ] Bestehende Tests + Integrationstests weiterhin grün; Default-Verhalten
      (Hetzner) unverändert.
- [ ] Doku beschreibt das Plugin-/Provider-Modell und das Schreiben eines
      eigenen Providers.
