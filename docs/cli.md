# CLI-Referenz

Die Installation stellt drei Kommandos bereit: `dnsjinja`, `explore_dns` und
`exit_on_error`.

## `dnsjinja`

```text
Usage: dnsjinja [OPTIONS]

  Modulare Verwaltung von DNS-Zonen (Backend über config.json wählbar)

Options:
  -d, --datadir TEXT     Basisverzeichnis für Templates und Konfiguration
                         (DNSJINJA_DATADIR)  [default: .]
  -c, --config TEXT      Konfigurationsdatei (DNSJINJA_CONFIG)  [default:
                         config/config.json]
  -u, --upload           Upload der Zonen
  -b, --backup           Backup der Zonen
  -w, --write            Zone-Files schreiben
  -C, --create-missing   Konfigurierte Domains, die beim Backend nicht
                         existieren, neu anlegen
  --auth-api-token TEXT  API-Token für das DNS-Backend
                         (DNSJINJA_AUTH_API_TOKEN, oder
                         DNSJINJA_<BACKEND>_AUTH_API_TOKEN)
  --dry-run              Zone-Files rendern und ausgeben, ohne zu schreiben
                         oder hochzuladen
  --dry-run-compare      Unterschiede zwischen Live-Daten des Backends und
                         Templates anzeigen, ohne etwas zu ändern
  --show-ttl             Bei --dry-run-compare auch reine TTL-Abweichungen
                         auflisten
  --help                 Show this message and exit.
```

### Optionen im Detail

| Option | Env-Variable | Beschreibung |
|--------|--------------|-------------|
| `-d`, `--datadir` | `DNSJINJA_DATADIR` | Daten-Repository (Templates, Config, Zone-Files). Standard: aktuelles Verzeichnis. |
| `-c`, `--config` | `DNSJINJA_CONFIG` | Pfad zur Konfigurationsdatei. Standard: `config/config.json`. |
| `-b`, `--backup` | – | Exportiert jede Zone vom Backend nach `zone-backups/`. |
| `-w`, `--write` | – | Schreibt die gerenderten Zone-Files nach `zone-files/`. |
| `-u`, `--upload` | – | Synchronisiert die Records mit der Zone beim Backend (RRSet-Sync, inkl. Löschen veralteter Records). |
| `-C`, `--create-missing` | – | Legt konfigurierte, aber beim Backend fehlende Domains als primäre Zone an. Ohne das Flag werden sie mit Warnung übersprungen. |
| `--auth-api-token` | `DNSJINJA_AUTH_API_TOKEN` | Bearer-Token. Wird ohne Angabe bei Bedarf abgefragt. |
| `--dry-run` | – | Rendert alle Zonen und gibt sie aus, ohne zu schreiben/hochzuladen. |
| `--dry-run-compare` | – | Vergleicht die Live-RRSets beim Backend mit den gerenderten Templates und zeigt die Unterschiede an, ohne etwas zu ändern. |
| `--show-ttl` | – | Listet bei `--dry-run-compare` auch RRSets auf, die ausschließlich in der TTL abweichen. |

!!! info "Feste Ausführungsreihenfolge"
    Die Flags `-b -w -u` können beliebig kombiniert werden; ausgeführt wird stets
    **Backup → Write → Upload**.

### Typische Aufrufe

```bash
# Trockenlauf: nur rendern und anzeigen
dnsjinja --dry-run

# Trockenlauf: Unterschiede zum Live-Stand beim Backend anzeigen
dnsjinja --dry-run-compare

# Voller Lauf: Backup, Schreiben, Upload
dnsjinja -b -w -u

# Fehlende Domains neu beim Backend anlegen und ausspielen
dnsjinja -C -b -w -u

# Mit explizitem Daten-Repository und Config
dnsjinja -d /pfad/zum/daten-repo -c config/config.json -b -w -u
```

### Ausgabe von `--dry-run-compare`

Der Vergleich liest die aktuellen RRSets jeder Zone über das Backend und stellt
sie den gerenderten Templates gegenüber. Es wird **nichts** geschrieben, hochgeladen
oder gelöscht – die Ausgabe entspricht exakt dem, was ein `-u`-Lauf tun würde.

```text
=== example.com ===
  ~ @/A  (TTL 300)
      - 192.0.2.1
      + 192.0.2.99
  + www/CNAME  (TTL 300)
      + example.com.
  - alt/A  (TTL 300)
      - 192.0.2.50
  ! locked/TXT  geschützt – wird beim Upload übersprungen
  1 neu, 2 geändert, 1 gelöscht, 1 geschützt, 8 unverändert
  Hinweis: 1 RRSet(s) weichen nur in der TTL ab. Sie sind oben ausgeblendet,
  werden beim Upload aber angeglichen – mit --show-ttl anzeigen.
```

| Zeichen | Bedeutung |
|---------|-----------|
| `+` | RRSet existiert beim Backend nicht und wird angelegt. |
| `~` | RRSet existiert, weicht aber im RDATA ab; eingerückte `-`/`+` zeigen die einzelnen Werte. |
| `-` | RRSet existiert nur beim Backend und würde beim Upload gelöscht. |
| `!` | RRSet ist beim Backend änderungsgeschützt und wird beim Upload übersprungen. |

Der `SOA`-Record bleibt außen vor – er wird vom Anbieter verwaltet. Bei deSEC gilt dasselbe zusätzlich für die DNSSEC-Typen.

#### TTL-Abweichungen

Die TTL wird in den Templates nicht pro Record gesetzt, sondern global über `$TTL`
vererbt. Reine TTL-Abweichungen sind darum selten beabsichtigt und werden in der
Ausgabe standardmäßig **ausgeblendet**; `--show-ttl` blendet sie wieder ein.

!!! warning "Der Upload gleicht die TTL trotzdem an"
    Das Ausblenden betrifft nur die Anzeige. Ein `-u`-Lauf setzt die TTL weiterhin
    auf den Template-Wert. Die Zusammenfassung weist mit einem `Hinweis:` darauf
    hin, wenn ausgeblendete TTL-Abweichungen vorliegen.

!!! note "Trockenlauf ändert nie etwas"
    `--dry-run` und `--dry-run-compare` schließen sich gegenseitig aus. In beiden
    Modi wird `--create-missing` ignoriert – ein Trockenlauf legt also auch mit `-C`
    keine Zonen beim Backend an.

## `explore_dns`

Erzeugt aus einem bestehenden Konto ein Gerüst für die `config.json` – alle
vorhandenen Zonen mit leerem `template`-Feld.

```text
Usage: explore_dns [OPTIONS]

  Vorhandene DNS-Zonen eines Backends auslesen

Options:
  -o, --output FILENAME   Ausgabedatei für die Ergebnisse
  -B, --dns-backend TEXT  DNS-Backend (DNSJINJA_DNS_BACKEND)  [default:
                          hetzner]
  --auth-api-token TEXT   API-Token für das DNS-Backend
                          (DNSJINJA_AUTH_API_TOKEN)
  --api-base TEXT         Basis-URL der API (DNSJINJA_API_BASE)
  --list-backends         Verfügbare DNS-Backends auflisten und beenden
  --help                  Show this message and exit.
```

```bash
# Auf stdout
explore_dns

# In eine Datei
explore_dns -o config/config.json
```

## `exit_on_error`

Hilfskommando für die Automatisierung: `dnsjinja` schreibt bei Upload-Fehlern einen
Exit-Code in eine temporäre Statusdatei und setzt den Lauf für die übrigen Domains
fort. `exit_on_error` liest diesen Status anschließend aus und beendet sich
entsprechend – so schlägt ein CI-Job fehl, wenn mindestens eine Domain nicht
aktualisiert werden konnte. Einsatz siehe [GitHub Actions](github-actions.md).

## Umgebungsvariablen

| Variable | Verwendet von | Beschreibung |
|----------|---------------|-------------|
| `DNSJINJA_AUTH_API_TOKEN` | alle | API-Token des DNS-Backends |
| `DNSJINJA_<BACKEND>_AUTH_API_TOKEN` | alle | Token je Backend, z. B. `DNSJINJA_DESEC_AUTH_API_TOKEN`; schlägt die allgemeine Variable |
| `DNSJINJA_DATADIR` | `dnsjinja` | Daten-Repository |
| `DNSJINJA_CONFIG` | `dnsjinja` | Pfad zur Konfigurationsdatei |
| `DNSJINJA_API_BASE` | `explore_dns` | Basis-URL der API (Standard: die des gewählten Backends) |
| `DNSJINJA_DNS_BACKEND` | `explore_dns` | DNS-Backend (Standard: `hetzner`) |

Variablen können auch in einer `.env`-Datei hinterlegt werden – siehe
[Installation](installation.md#umgebungsvariablen).
