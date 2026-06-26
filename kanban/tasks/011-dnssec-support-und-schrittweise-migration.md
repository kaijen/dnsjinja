---
id: 11
title: 'DNSSEC-Support + schrittweise DNS-Migration zu DNSSEC-fähigem Provider'
status: backlog
priority: high
created: 2026-06-26T12:00:00+02:00
updated: 2026-06-26T12:00:00+02:00
depends_on:
    - 9
    - 10
tags:
    - dnssec
    - migration
    - provider
    - architecture
class: standard
---

## Ziel & Kontext

Aktuell liegt das **DNS aller Domains bei Hetzner** (kein/ungewünschtes
DNSSEC). Ziel ist die **schrittweise** Migration des DNS-Hostings – Domain
für Domain – zu einem **DNSSEC-fähigen** DNS-Provider, ohne Big-Bang und mit
jederzeit klarem, zurückrollbarem Zustand.

Wichtig: Die **Registrierung** (Feld `registrar`, wo die Domain bezahlt wird)
bleibt unverändert. Migriert wird nur das **DNS-Hosting** (`provider` aus
#10). Beim Registrar ändern sich pro Domain nur zwei Dinge: die delegierten
**NS-Records** und der **DS-Record** (DNSSEC-Vertrauensanker).

Abhängigkeiten:
- **#9** liefert das Provider-Interface (DNS-API hinter Plugin).
- **#10** liefert Multiprovider/Per-Domain-Routing – die technische
  Voraussetzung, um *einzelne* Domains auf den neuen Provider zu schieben,
  während der Rest noch bei Hetzner bleibt.
Dieses Ticket ergänzt die **DNSSEC-Dimension** + den **Migrations-Workflow**.

## Teil A – DNSSEC im Provider-Modell

### A1. Capability-Flag

`DnsProvider` (aus #9) um Capability erweitern, z. B.
`supports_dnssec: bool` bzw. eine `capabilities`-Menge. Kern und Migrations-
Tooling können so prüfen, ob ein Zielprovider DNSSEC kann.

### A2. Sync darf signaturverwaltete RRSets NICHT anfassen

`_sync_zone_rrsets()` löscht heute „stale" RRSets, die nicht im gerenderten
Zustand stehen. SOA wird bereits ausgenommen. Bei DNSSEC **provider-
verwaltete** Typen MÜSSEN ebenfalls ausgenommen werden, sonst löscht/zerstört
der Sync die Signatur-Infrastruktur:

- Ausschlussliste erweitern um: `DNSKEY`, `RRSIG`, `NSEC`, `NSEC3`,
  `NSEC3PARAM`, `CDS`, `CDNSKEY` (und `SOA` wie bisher).
- Diese Records werden vom signierenden Provider automatisch erzeugt; der
  gerenderte Zonentext enthält sie nicht → ohne Ausschluss würde der
  Delete-Pass sie als „verwaist" entfernen wollen.
- Test: Zone beim (Fake-)Provider hat DNSKEY/RRSIG; Sync lässt sie unberührt.

### A3. DS-/Schlüssel-Material auslesbar machen

Neue (optionale) Interface-Methode, z. B.
`get_dnssec_ds(zone) -> list[DS]` / `get_dnssec_keys(zone)`, damit nach
Aktivierung am neuen Provider der **DS-Record** für den Registrar ermittelt
werden kann. Provider, die kein DNSSEC können, geben „nicht unterstützt"
zurück (analog Zonefile-Export-Capability in #9).

### A4. Grenze zum Registrar

Das **Publizieren** von DS- und NS-Änderungen passiert beim **Registrar**
(eigene API oder manuell) – nicht in der DNS-Provider-API. Dieses Ticket:
- stellt den DS-Wert maschinenlesbar bereit (Ausgabe/Report),
- dokumentiert den manuellen/registrar-seitigen Schritt klar.
Eine Registrar-API-Anbindung (automatisches DS/NS-Setzen) ist **out of
scope** (eigenes Folge-Ticket; einige Registrare inkl. Hetzner bieten APIs).

## Teil B – Migrations-Workflow (pro Domain)

Sollzustand-Runbook, das das Tooling unterstützen soll:

1. **Zielzone anlegen**: Domain in `config.json` auf neuen `provider` (#10)
   zeigen lassen; Records dorthin rendern/syncen (`-u`). Hetzner bleibt
   parallel aktiv.
2. **Parität prüfen** (NEU, siehe B1): Records am neuen Provider == bisheriger
   Stand? Erst weiter, wenn deckungsgleich.
3. **DNSSEC aktivieren** am neuen Provider (oft automatisch, z. B. deSEC
   signiert by default) und **DS auslesen** (A3).
4. **Registrar**: NS auf die Nameserver des neuen Providers umstellen; nach
   Propagation **DS** publizieren (A4).
5. **Verifizieren**: Auflösung über neue NS korrekt, DNSSEC-Validierung grün
   (AD-Bit), Serial konsistent.
6. **Hetzner-Zone stilllegen** (Backup vorher via #9-Export, sofern Provider
   das kann) und aus dem Hetzner-Routing nehmen.

Reihenfolge ist bewusst reversibel: bis Schritt 4 (NS/DS) ist der alte Stand
unverändert autoritativ.

### B1. Paritäts-/Diff-Modus (neues Feature)

Read-only-Vergleich, der vor dem NS-Cutover Vertrauen schafft:
- Vergleicht gerenderte Soll-RRSets bzw. die Zone des Alt-Providers gegen die
  Zone des Ziel-Providers und meldet Abweichungen (fehlende/zusätzliche/
  abweichende RRSets), DNSSEC-Typen dabei ausgenommen (A2).
- Als CLI-Modus, z. B. `--diff` / `--verify-parity` (analog `--dry-run`),
  über das Provider-Interface – provider-neutral.

### B2. Serial-/SOA-Ermittlung während der Migration

Stolperstein: `_get_zone_serial()` / `_new_zone_serial()` lesen den SOA-Serial
über die **global** konfigurierten `name-servers` (Resolver). Während der
Migration ist die autoritative Quelle einer Domain provider-abhängig:
- Eine schon migrierte Domain über die alten (Hetzner-)NS abzufragen liefert
  veraltete/keine Daten → falscher/abbrechender Serial.
- Lösung: SOA-Serial **pro Domain** an der richtigen Quelle ermitteln –
  bevorzugt direkt beim zuständigen Provider (Interface) bzw. über die für
  die Domain zuständigen NS, statt global fixer Resolver.
- Test deckt: migrierte vs. nicht-migrierte Domain liefern je korrekten
  Serial.

## Zielprovider-Kandidaten (offen)

Provider-neutral umsetzen; konkretes erstes DNSSEC-Plugin ist zu wählen.
Kandidaten u. a. **deSEC** (DNSSEC by default, freie API, DS via API – guter
Startkandidat), Cloudflare, INWX, PowerDNS. → Klärung mit Nutzer, welches
Plugin zuerst gebaut wird (eigenes Plugin-Ticket nach #9).

## Tests

- A2: Sync lässt DNSKEY/RRSIG/NSEC*/CDS/CDNSKEY am Provider unberührt
  (FakeProvider mit vorhandenen Signatur-RRSets).
- A3: DS/Schlüssel auslesbar; Provider ohne DNSSEC meldet „nicht
  unterstützt" sauber.
- B1: Diff-Modus erkennt fehlende/zusätzliche/abweichende RRSets; ignoriert
  DNSSEC-Typen; läuft read-only.
- B2: Per-Domain-Serial korrekt für migrierte und nicht-migrierte Domain.
- Migrations-Smoke (mit FakeProvidern „hetzner" + „desec"): eine Domain
  wechselt `provider`, Parität grün, DS abrufbar, Alt-Zone bleibt bis Cutover
  unangetastet.

## Rückwärtskompatibilität

- Ohne DNSSEC-Provider / ohne Migration ändert sich nichts am Verhalten.
- A2 (Ausschluss der Signatur-Typen) ist auch ohne aktive Migration korrekt
  und schadet bestehenden Hetzner-Zonen nicht.

## Risiken / offene Punkte

- DS-Timing: DS erst publizieren, wenn DNSKEY am neuen Provider live & NS
  umgestellt – sonst Validierungs-Bruch (SERVFAIL). Runbook muss die
  Reihenfolge betonen.
- Unterschiedliche DNSSEC-Modelle der Provider (managed signing vs.
  CDS/CDNSKEY-Automatik nach RFC 7344/8078) – Interface generisch halten.
- TTL-Absenkung vor Cutover (NS/SOA) zur schnelleren Propagation –
  Runbook-Hinweis.
- Registrar-Schritt bleibt teils manuell (out of scope, siehe A4).

## Akzeptanzkriterien

- [ ] `_sync_zone_rrsets()` fasst SOA + DNSSEC-Typen (DNSKEY, RRSIG, NSEC,
      NSEC3, NSEC3PARAM, CDS, CDNSKEY) nicht an; durch Test abgesichert.
- [ ] Provider-Interface meldet DNSSEC-Capability und liefert DS-/Schlüssel-
      Material (sofern unterstützt).
- [ ] Paritäts-/Diff-Modus vergleicht Ziel-Provider gegen Soll/Alt-Provider
      read-only und ist provider-neutral.
- [ ] SOA-Serial wird pro Domain an der korrekten autoritativen Quelle
      ermittelt (migrierte und nicht-migrierte Domain korrekt).
- [ ] Migrations-Runbook (Domain für Domain, reversibel bis NS/DS-Cutover)
      dokumentiert; Registrar-Schritt klar als manuell/Folge-Ticket markiert.
