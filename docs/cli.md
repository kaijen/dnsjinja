# CLI-Referenz

Die Installation stellt drei Kommandos bereit: `dnsjinja`, `explore_hetzner` und
`exit_on_error`.

## `dnsjinja`

```text
Usage: dnsjinja [OPTIONS]

  Modulare Verwaltung von DNS-Zonen (Hetzner Cloud API)

Options:
  -d, --datadir TEXT     Basisverzeichnis für Templates und Konfiguration
                         (DNSJINJA_DATADIR)  [default: .]
  -c, --config TEXT      Konfigurationsdatei (DNSJINJA_CONFIG)  [default:
                         config/config.json]
  -u, --upload           Upload der Zonen
  -b, --backup           Backup der Zonen
  -w, --write            Zone-Files schreiben
  -C, --create-missing   Konfigurierte Domains, die bei Hetzner nicht
                         existieren, neu anlegen
  --auth-api-token TEXT  API-Token (Bearer) für Hetzner Cloud API
                         (DNSJINJA_AUTH_API_TOKEN)
  --dry-run              Zone-Files rendern und ausgeben, ohne zu schreiben
                         oder hochzuladen
  --help                 Show this message and exit.
```

### Optionen im Detail

| Option | Env-Variable | Beschreibung |
|--------|--------------|-------------|
| `-d`, `--datadir` | `DNSJINJA_DATADIR` | Daten-Repository (Templates, Config, Zone-Files). Standard: aktuelles Verzeichnis. |
| `-c`, `--config` | `DNSJINJA_CONFIG` | Pfad zur Konfigurationsdatei. Standard: `config/config.json`. |
| `-b`, `--backup` | – | Exportiert jede Zone von Hetzner nach `zone-backups/`. |
| `-w`, `--write` | – | Schreibt die gerenderten Zone-Files nach `zone-files/`. |
| `-u`, `--upload` | – | Synchronisiert die Records mit der Hetzner-Zone (RRSet-Sync, inkl. Löschen veralteter Records). |
| `-C`, `--create-missing` | – | Legt konfigurierte, aber bei Hetzner fehlende Domains als primäre Zone an. Ohne das Flag werden sie mit Warnung übersprungen. |
| `--auth-api-token` | `DNSJINJA_AUTH_API_TOKEN` | Bearer-Token. Wird ohne Angabe bei Bedarf abgefragt. |
| `--dry-run` | – | Rendert alle Zonen und gibt sie aus, ohne zu schreiben/hochzuladen. |

!!! info "Feste Ausführungsreihenfolge"
    Die Flags `-b -w -u` können beliebig kombiniert werden; ausgeführt wird stets
    **Backup → Write → Upload**.

### Typische Aufrufe

```bash
# Trockenlauf: nur rendern und anzeigen
dnsjinja --dry-run

# Voller Lauf: Backup, Schreiben, Upload
dnsjinja -b -w -u

# Fehlende Domains neu bei Hetzner anlegen und ausspielen
dnsjinja -C -b -w -u

# Mit explizitem Daten-Repository und Config
dnsjinja -d /pfad/zum/daten-repo -c config/config.json -b -w -u
```

## `explore_hetzner`

Erzeugt aus einem bestehenden Hetzner-Account ein Gerüst für die `config.json` – alle
vorhandenen Zonen mit leerem `template`-Feld.

```text
Usage: explore_hetzner [OPTIONS]

  Explore Hetzner DNS Zones (Cloud API)

Options:
  -o, --output FILENAME  Ausgabedatei für die Ergebnisse
  --auth-api-token TEXT  API-Token (Bearer) für Hetzner Cloud API
                         (DNSJINJA_AUTH_API_TOKEN)
  --api-base TEXT        Basis-URL der Hetzner Cloud API (DNSJINJA_API_BASE)
  --help                 Show this message and exit.
```

```bash
# Auf stdout
explore_hetzner

# In eine Datei
explore_hetzner -o config/config.json
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
| `DNSJINJA_AUTH_API_TOKEN` | alle | Bearer-Token der Hetzner Cloud API |
| `DNSJINJA_DATADIR` | `dnsjinja` | Daten-Repository |
| `DNSJINJA_CONFIG` | `dnsjinja` | Pfad zur Konfigurationsdatei |
| `DNSJINJA_API_BASE` | `explore_hetzner` | Basis-URL der API (Standard: `https://api.hetzner.cloud/v1`) |

Variablen können auch in einer `.env`-Datei hinterlegt werden – siehe
[Installation](installation.md#umgebungsvariablen).
