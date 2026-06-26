---
id: 10
title: 'Multiprovider: Domains gleichzeitig über verschiedene DNS-Provider verwalten'
status: backlog
priority: high
created: 2026-06-26T11:30:00+02:00
updated: 2026-06-26T11:30:00+02:00
depends_on:
    - 9
tags:
    - architecture
    - plugin
    - provider
    - multiprovider
class: standard
---

## Ziel

`dnsjinja` so erweitern, dass innerhalb **eines** Laufs / **einer**
`config.json` verschiedene Domains über **verschiedene** DNS-Provider
verwaltet werden können (z. B. Domain A bei Hetzner, Domain B bei deSEC,
Domain C bei INWX) – jeweils mit eigenen Zugangsdaten und API-Endpunkten.

Baut direkt auf **#9 (Provider-Abstraktion via Plugin)** auf. #9 macht *einen*
Provider austauschbar; dieses Ticket macht *mehrere* Provider gleichzeitig
nutzbar und ordnet jede Domain ihrem Provider zu.

## Abgrenzung zu #9

- **#9**: Ein Provider pro Lauf, hinter `DnsProvider`-Interface, per
  Config/Plugin austauschbar. `DNSJinja` hält genau ein `self.provider`.
- **#10 (dieses Ticket)**: N Provider pro Lauf. Routing pro Domain auf eine
  von mehreren Provider-Instanzen; pro Provider eigene Credentials.

Hard-Dependency: #10 nicht beginnen, bevor das `DnsProvider`-Interface +
Registry aus #9 steht.

## Motivation

- **Wichtig – `registrar` ≠ DNS-Provider:** Das `registrar`-Feld in
  `testdata/config/config.json` (Hetzner, Namecheap, GoDaddy …) bezeichnet,
  **wo die Domain registriert/bezahlt** wird, NICHT wo das DNS gehostet wird.
  Beides ist orthogonal (Domain bei Namecheap registriert, DNS bei Hetzner).
  Aktuell liegt das **DNS aller Domains bei Hetzner**; `registrar` ist davon
  unabhängig. Multiprovider trennt genau diese Achse: das DNS-Hosting wird
  pro Domain wählbar, unabhängig vom Registrar.
- Konkreter Anlass (siehe #11): schrittweise DNS-Migration von Hetzner zu
  einem DNSSEC-fähigen DNS-Provider – Domain für Domain, ohne mehrere
  getrennte Configs/Läufe/Tokens.

## Designänderungen gegenüber dem Einzel-Provider-Modell

### 1. Mehrere Provider-Instanzen statt `self.provider`

- Neuer `ProviderPool` (z. B. `providers/pool.py`): hält pro **benannter
  Provider-Konfiguration** eine instanziierte `DnsProvider`-Instanz, lazy
  erzeugt und gecacht. Schlüssel ist der Konfig-Name (nicht der Plugin-Typ),
  damit z. B. zwei Hetzner-Accounts mit unterschiedlichen Tokens nebeneinander
  möglich sind.
- `DNSJinja` hält `self.providers: ProviderPool` statt `self.provider`.

### 2. Konfiguration

Neuer benannter Provider-Block plus per-Domain-Zuordnung:

    {
      "global": {
        "providers": {
          "hetzner-main": {
            "plugin": "hetzner",
            "api-base": "https://api.hetzner.cloud/v1",
            "token-env": "DNSJINJA_TOKEN_HETZNER_MAIN"
          },
          "desec": {
            "plugin": "desec",
            "token-env": "DNSJINJA_TOKEN_DESEC"
          }
        },
        "default-provider": "hetzner-main"
      },
      "domains": {
        "example.com":  { "template": "standard.tpl", "provider": "desec" },
        "example.org":  { "template": "standard.tpl" }
      }
    }

- `global.providers`: Map *Name → Provider-Definition* (`plugin` = Plugin-
  Kennung aus #9, plus provider-spezifische Optionen / Endpoint / Credential-
  Referenz).
- `global.default-provider`: greift für Domains ohne explizites `provider`.
- `domains.<name>.provider`: optionaler Verweis auf einen Namen aus
  `global.providers`.
- Validierung (Pydantic): jeder `domains.*.provider` und
  `default-provider` muss in `global.providers` existieren – sonst klarer
  Konfig-Fehler beim Start.

### 3. Credentials pro Provider

- Einzelnes `--auth-api-token` / `DNSJINJA_AUTH_API_TOKEN` reicht nicht mehr.
- Pro Provider-Definition Referenz auf eine Umgebungsvariable (`token-env`)
  oder Credential über `provider-options`. Mehrere Tokens parallel.
- Rückwärtskompatibilität: Ist kein `global.providers` gesetzt, wird aus
  `default-provider`/Legacy-Feldern + `--auth-api-token` implizit **ein**
  Default-Provider "hetzner" gebildet (Verhalten wie nach #9).
- Klare Fehlermeldung, wenn die referenzierte Token-Env fehlt – inkl.
  Provider-Name.

### 4. Routing & gruppierte Provider-Aufrufe

- `_prepare_zones()` darf nicht mehr „alle Zonen von einem Client" annehmen.
  Domains nach Provider-Instanz **gruppieren**, dann pro Provider **einmal**
  `list_zones()` aufrufen (Effizienz, vermeidet N Einzelabfragen).
- Der „bei Provider eingerichtet, aber nicht konfiguriert"-Hinweis aus
  `_prepare_zones()` muss pro Provider berechnet werden (sonst falsche
  Warnungen, weil deSEC-Zonen nicht in der Hetzner-Liste stehen).
- `upload_zones()` / `backup_zones()` / `_sync_zone_rrsets()` routen pro
  Domain auf `self.providers[domain]`.

### 5. Fehler-Isolierung

- Ein Ausfall (Auth/Netz) eines Providers darf die Domains der anderen
  Provider **nicht** abbrechen. Pro Provider-Gruppe isoliert behandeln und am
  Ende sammeln; Exit-Code-Logik (`exit_on_error`/254) entsprechend
  aggregieren statt beim ersten Fehler global abzubrechen.

## Refactoring-Schritte

1. Config-Schema erweitern: `global.providers`, `global.default-provider`,
   `domains.*.provider`; Querverweis-Validierung.
2. `ProviderPool` + Credential-Auflösung (Env-Refs) implementieren.
3. `DNSJinja.__init__`: Pool statt Einzel-Provider; jeder Domain ihre Instanz
   zuordnen (`self._provider_for: dict[str, DnsProvider]`).
4. `_prepare_zones()` auf Gruppierung-pro-Provider umstellen.
5. `upload/backup/sync`-Pfade auf Per-Domain-Routing umstellen.
6. Fehler-Isolierung + aggregierte Exit-Codes.
7. CLI: `--auth-api-token` bleibt als Legacy-/Single-Provider-Shortcut;
   Doku erklärt das `token-env`-Modell für Multiprovider.
8. Doku (`README`, `docs/konfiguration.md`, `AGENT.md`): Multiprovider-Setup,
   Beispiel-Config, Credential-Handling.

## Tests

- **FakeProvider** (aus #9) in **zwei Instanzen** mit unterschiedlichen
  Zonenbeständen: Domains korrekt geroutet; keine Cross-Provider-Lecks bei
  „konfiguriert/nicht eingerichtet"-Warnungen.
- Config-Validierung: unbekannter `provider`-Verweis / fehlende `token-env`
  → klarer Fehler.
- Fehler-Isolierung: Provider A wirft `ProviderError`, Provider-B-Domains
  werden trotzdem vollständig verarbeitet; Exit-Code spiegelt Teilfehler.
- Effizienz/Gruppierung: `list_zones()` wird pro Provider genau einmal
  aufgerufen (nicht pro Domain).
- Rückwärtskompatibilität: bestehende Single-Provider-`config.json` (ohne
  `global.providers`) läuft unverändert über den impliziten Default.

## Rückwärtskompatibilität

- Ohne `global.providers`/`domains.*.provider` identisches Verhalten wie nach
  #9 (ein Hetzner-Default, `--auth-api-token`).
- `registrar` (Bezahl-/Registrierungsstelle) und `provider` (DNS-Hosting)
  sind orthogonal und werden NICHT verknüpft. `registrar` bleibt reine
  Metadaten; `provider` ist das technische, funktionale Feld für das
  DNS-Routing. `registrar` taugt ausdrücklich NICHT als Default für
  `provider`.

## Risiken / offene Punkte

- Serial-/SOA-Logik (`_new_zone_serial` via DNS-Resolver) ist provider-
  unabhängig und bleibt – prüfen, dass Multiprovider daran nichts ändert.
- Provider mit/ohne Zonefile-Export gemischt: Backup pro Domain nach
  Capability des jeweiligen Providers entscheiden (siehe #9).
- Parallelisierung pro Provider (Performance) bewusst **out of scope** –
  erst korrektes serielles Routing, Optimierung später.
- Secrets: nur Env-Referenzen in der Config, keine Klartext-Tokens.

## Akzeptanzkriterien

- [ ] Eine `config.json` kann Domains auf mehrere benannte Provider verteilen;
      jede Domain wird über ihre Provider-Instanz verwaltet.
- [ ] Pro Provider eigene Credentials (getrennte Token-Envs), inkl. zweier
      Accounts desselben Plugins.
- [ ] `list_zones()` wird pro Provider einmal aufgerufen; „nicht
      konfiguriert"-Warnungen sind provider-lokal korrekt.
- [ ] Ein Provider-Ausfall isoliert die übrigen Provider nicht; Exit-Code
      aggregiert Teilfehler korrekt.
- [ ] Bestehende Single-Provider-Configs laufen unverändert.
- [ ] Doku beschreibt Multiprovider-Config + Credential-Modell mit Beispiel.
