# Schnellstart

Dieser Schnellstart führt vom API-Token bis zum ersten Upload – anhand des
mitgelieferten anonymisierten Datensatzes aus `samples/`.

## 1. API-Token erstellen

Erstelle in der [Hetzner Cloud Console](https://console.hetzner.cloud/) im jeweiligen
Projekt unter **Security → API Tokens** ein Token mit **Read & Write**.

```bash
export DNSJINJA_AUTH_API_TOKEN=<dein-token>
```

!!! warning "Nur Cloud-API-Token"
    Es muss ein **Cloud-API-Token** (`api.hetzner.cloud`) sein. Alte
    `Auth-API-Token` aus der DNS-Konsole (`dns.hetzner.com`) werden abgelehnt.

## 2. Daten-Repository anlegen

`dnsjinja` erwartet eine feste Verzeichnisstruktur. Am einfachsten beginnst du mit
dem Beispiel-Datensatz aus `samples/`:

```bash
git clone https://github.com/kaijen/dnsjinja.git
cp -r dnsjinja/samples mein-dns
cd mein-dns
mv config.json.sample config/config.json   # ggf. Verzeichnis anlegen
mkdir -p zone-files zone-backups
```

Die erwartete Struktur:

```
mein-dns/
├── config/
│   └── config.json          # Konfiguration
├── templates/
│   ├── standard.tpl         # Haupt-Template
│   └── include/             # modulare Includes
├── zone-files/              # erzeugte Zone-Files (nicht versioniert)
└── zone-backups/            # Backups von Hetzner (nicht versioniert)
```

## 3. Konfiguration aus dem Hetzner-Account erzeugen (optional)

Existieren bereits Zonen bei Hetzner, erzeugt `explore_dns` ein Gerüst für die
`config.json`:

```bash
explore_dns -o config/config.json
```

Die Ausgabe enthält alle vorhandenen Domains mit leerem `template`-Feld, das du dann
ausfüllst. Details unter [Konfiguration](konfiguration.md).

## 4. Trockenlauf

`--dry-run` rendert alle Zonen und gibt sie auf der Konsole aus, **ohne** zu schreiben
oder hochzuladen – ideal zum Prüfen:

```bash
dnsjinja -d . -c config/config.json --dry-run
```

`--dry-run-compare` geht einen Schritt weiter und zeigt statt der gerenderten Zonen
die **Unterschiede zum Live-Stand bei Hetzner** – also genau die Änderungen, die ein
Upload vornehmen würde:

```bash
dnsjinja -d . -c config/config.json --dry-run-compare
```

## 5. Schreiben & Hochladen

Der typische Lauf kombiniert Backup, Schreiben und Upload:

```bash
dnsjinja -d . -c config/config.json -b -w -u
```

| Flag | Wirkung |
|------|---------|
| `-b` / `--backup` | bestehende Zone von Hetzner nach `zone-backups/` exportieren |
| `-w` / `--write`  | gerenderte Zone-Files nach `zone-files/` schreiben |
| `-u` / `--upload` | Records mit der Hetzner-Zone synchronisieren |

!!! info "Reihenfolge ist fest"
    Unabhängig von der Flag-Reihenfolge führt `dnsjinja` immer **Backup → Write →
    Upload** aus. So liegt vor jeder Änderung ein Backup vor.

## Was beim Upload passiert

`dnsjinja` gleicht die gerenderten Records mit der Zone bei Hetzner ab
(*RRSet-Sync*): fehlende Records werden angelegt, geänderte aktualisiert und
**Records, die nicht mehr im Template stehen, werden gelöscht**. Die `config.json` und
die Templates sind damit die maßgebliche Quelle für den Zonen-Inhalt.

!!! danger "Upload ist destruktiv"
    Beim ersten echten Upload werden alle nicht im Template enthaltenen Records der
    Zone entfernt. Prüfe vorher mit `--dry-run-compare`, welche Records konkret
    angelegt, geändert und gelöscht würden, und verlasse dich auf das automatische
    Backup in `zone-backups/`.

Weiter mit dem [vollständigen Beispiel](beispiel.md), das zeigt, wie aus Konfiguration
und Includes ein konkretes Zone-File entsteht.
