---
id: 12
title: 'deSEC-Provider-Plugin implementieren (DNSSEC-fähiges DNS-Hosting)'
status: backlog
priority: high
created: 2026-06-26T12:30:00+02:00
updated: 2026-06-26T12:30:00+02:00
depends_on:
    - 9
tags:
    - plugin
    - provider
    - desec
    - dnssec
    - http
class: standard
---

## Ziel

Ein `DnsProvider`-Plugin für **deSEC** (desec.io) implementieren –
`src/dnsjinja/providers/desec.py`, `DesecProvider(DnsProvider)`. deSEC ist
der angepeilte DNSSEC-fähige DNS-Provider für die schrittweise Migration weg
von Hetzner. Das Plugin erfüllt das Interface aus **#9**, ist über die
Registry/Entry-Points ladbar und im Multiprovider-Betrieb (**#10**) parallel
zu Hetzner nutzbar.

## Abhängigkeiten

- **#9** (Provider-Interface + Registry): Hard-Dependency – ohne `DnsProvider`,
  `Zone`, `RRSet`, `ProviderError` und `load_provider` nicht umsetzbar.
- **#10**: ermöglicht den parallelen Betrieb deSEC + Hetzner; nicht zwingend
  für die reine Plugin-Implementierung, aber Zielkontext.
- **#11**: liefert die DNSSEC-Erweiterungen am Interface (`supports_dnssec`,
  `get_dnssec_ds`, Schutz der Signatur-RRSets). Die DNSSEC-spezifischen
  Methoden dieses Plugins (DS-Abruf) hängen an A1/A3 aus #11.

> Hinweis: Alle u. g. API-Details gegen die **aktuelle** deSEC-API-Doku
> (https://desec.readthedocs.io) verifizieren, bevor implementiert wird.

## deSEC-API – relevante Eckpunkte

- **Base-URL**: `https://desec.io/api/v1/`
- **Auth**: Token, Header `Authorization: Token <token>`. Über
  `provider-options`/`token-env` aus #10 (kein Bearer wie bei Hetzner).
- **Domains/Zonen**:
  - `GET /domains/` (Liste, **cursor-paginiert** via `Link`-Header – Folgen!)
  - `POST /domains/` Body `{"name": "<zone>"}` (deSEC kennt kein
    `mode="primary"` wie Hetzner)
  - `GET /domains/{name}/` – enthält `keys` (DNSSEC: `ds[]`, `dnskey`)
  - `DELETE /domains/{name}/`
- **RRSets**: `GET/POST /domains/{name}/rrsets/`,
  Einzel-RRSet `…/rrsets/{subname}/{type}/` (GET/PATCH/PUT/DELETE):
  - Felder: `subname`, `type`, `ttl`, `records: list[str]`.
  - **Löschen** = `DELETE` der RRSet **oder** `records: []` setzen.
  - **Bulk** über `PATCH`/`PUT` auf `…/rrsets/` mit Array (effizienter als
    N Einzelcalls – siehe Mapping-Strategie unten).
- **DNSSEC**: deSEC **signiert automatisch** (immer an, nicht abschaltbar) →
  `supports_dnssec = True`; DS kommt aus `domain.keys[].ds`.

## Mapping deSEC ↔ dnsjinja-Kernmodell

| Kern (#9 `RRSet`)        | deSEC                                   |
|--------------------------|-----------------------------------------|
| `name` = `@` (Apex)      | `subname = ""` (leerer String)          |
| `name` = `www`           | `subname = "www"`                       |
| `records` (FQDN, Punkt)  | `records` (Presentation, FQDN m. Punkt) |
| `ttl`                    | `ttl` (Achtung Mindest-TTL, s. u.)      |

- **Apex-Mapping** `@` ↔ `""` ist der wichtigste Stolperstein. dnsjinja-Kern
  nutzt seit #8 `@` als Owner und FQDN-Ziele mit Punkt (`relativize=False`) –
  das passt gut zu deSECs Presentation-Format; nur `subname` muss übersetzt
  werden.
- **Mindest-TTL**: deSEC erzwingt eine Konto-/Domain-`minimum_ttl` (oft
  3600). TTLs unterhalb werden mit `400` abgelehnt. Plugin muss das als
  klaren `ProviderError` mit verständlicher Meldung mappen (nicht roher
  HTTP-Fehler) – ggf. Hinweis „Template-TTL < deSEC-Minimum".

## Interface-Implementierung (`DesecProvider`)

- `name = "desec"`, `supports_dnssec = True`.
- `list_zones()` → paginierte `GET /domains/`, Map `name -> Zone(handle=…)`.
- `create_zone(name)` → `POST /domains/`.
- `get_rrsets(zone)` → paginierte RRSet-Liste → `list[RRSet]`; `subname=""`
  zurück auf `@` mappen. SOA/DNSSEC-Typen liefert deSEC i. d. R. ohnehin nicht
  als editierbare RRSets, der Kern filtert zusätzlich (siehe #11 A2).
- `create_rrset` / `set_rrset_records` / `set_rrset_ttl` / `delete_rrset`
  über die RRSet-Endpunkte. **Empfohlen**: in `_sync_zone_rrsets` (Kern) bleibt
  die Diff-Logik; das Plugin kann zur Effizienz intern Bulk-`PATCH` nutzen,
  muss aber die Einzelmethoden-Semantik des Interface erfüllen.
- `export_zonefile(zone)` → deSEC bietet **keinen** nativen Zonefile-Export.
  Optionen: (a) Capability „nicht unterstützt" melden (Backup-Skip wie in #9),
  oder (b) Zonefile aus den RRSets **synthetisieren**. Entscheidung im Ticket:
  zunächst (a) sauber melden; (b) optional als Folgeschritt.
- `get_dnssec_ds(zone)` (aus #11 A3) → aus `GET /domains/{name}/` `keys[].ds`.

## Fehler-Mapping

Native HTTP-Fehler → `ProviderError`-Hierarchie aus #9:
- `401/403` → `ProviderAuthError`
- `404` → `ProviderNotFoundError`
- `429` (Throttling, `Retry-After`) → `ProviderTransientError` (mit Backoff;
  deSEC rate-limited spürbar)
- `400` (z. B. TTL/Validierung) → `ProviderError` mit deSEC-Fehlertext
- `5xx`/Netzfehler → `ProviderTransientError`

## Abhängigkeiten / Packaging

- HTTP-Client: deSEC hat keinen offiziellen Python-SDK in den Deps. Direkt
  über `httpx` (bevorzugt) oder `requests`. Als **optionales** Extra
  einbinden (`[project.optional-dependencies] providers-desec`), analog zur
  hcloud-Trennung in #9 – der Kern bleibt importierbar ohne deSEC-Deps.
- Entry-Point registrieren:

      [project.entry-points."dnsjinja.providers"]
      desec = "dnsjinja.providers.desec:DesecProvider"

## Tests

- **Mit gemocktem HTTP** (respx/responses o. Ä.), keine Live-Calls in den
  Unit-Tests:
  - Pagination über mehrere Seiten korrekt zusammengeführt.
  - Apex-Mapping `@` ↔ `subname=""` in beide Richtungen.
  - CRUD: create/set-records/set-ttl/delete erzeugen die richtigen Requests.
  - Fehler-Mapping: 401/404/429/400 → richtige `ProviderError`-Subtypen;
    429 respektiert `Retry-After`.
  - Mindest-TTL: TTL < Minimum → verständlicher `ProviderError`.
  - `get_dnssec_ds` parst `keys[].ds`.
- **Registry**: `load_provider("desec")` instanziiert `DesecProvider`.
- **FakeProvider-Parität**: deSEC-Plugin erfüllt dieselben Interface-Kontrakte
  wie der FakeProvider (gemeinsame Contract-Tests, falls in #9 vorhanden).
- **Integrationstest** (Marker `integration`, optional): gegen eine echte
  deSEC-Testdomain mit eigenem Token (`DNSJINJA_TOKEN_DESEC`), analog zu den
  bestehenden Hetzner-Integrationstests. Standardmäßig übersprungen.

## Akzeptanzkriterien

- [ ] `DesecProvider` erfüllt das `DnsProvider`-Interface aus #9 und ist über
      Entry-Point/Registry als `"desec"` ladbar.
- [ ] Apex (`@` ↔ `""`), FQDN-Records und TTL korrekt gemappt; Pagination
      vollständig gefolgt.
- [ ] HTTP-Fehler sauber auf `ProviderError`-Subtypen gemappt (inkl.
      429/Retry-After und Mindest-TTL-Fall).
- [ ] `supports_dnssec = True`; DS über `get_dnssec_ds` abrufbar (#11 A3).
- [ ] `export_zonefile` meldet „nicht unterstützt" sauber (Backup-Skip) –
      kein Crash.
- [ ] `httpx`/Client als optionales Extra; Kern bleibt ohne deSEC-Deps
      importierbar.
- [ ] Unit-Tests mit gemocktem HTTP grün; optionaler Integrationstest
      vorhanden und standardmäßig übersprungen.
