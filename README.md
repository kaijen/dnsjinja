# DNSJinja zum Erstellen von Bind9-Zone-Files

`dnsjinja` ist ein Python-Script, das mit Hilfe von [Jinja](https://palletsprojects.com/p/jinja/) aus modularen
Template-Dateien Bind9-kompatible Zone-Files erzeugt.

Diese Zone-Files sollten genutzt werden, um die DNS-Konfiguration per [Hetzner REST API](https://dns.hetzner.com/api-docs) bei Hetzner einzuspielen.

## Installation

`dnsjinja` kann mit einem aktuellen Python genutzt werden bei dem die Module aus `requirements.txt` installiert sind.
Es ist empfohlen, dafür eine [virtuelle Python Umgebung](https://realpython.com/python-virtual-environments-a-primer/) zu nutzen. Bei der Installation von `dnsjinja` mit `pip` werden alle benötigten Abhängigkeiten installiert.

Nach Aktivierung der virtuellen Python Umgebung sollte `dnsjinja` dort aus github mit
`pip install git+ssh://git@github.com/kaijen/dnsjinja.git` oder `pip install git+https://github.com/kaijen/dnsjinja.git` installiert werden.

Dabei wird innerhalb der virtuellen Umgebung eine ausführbare Datei erzeugt, über die die Verwaltung der Domänen auf der Kommandozeile mit `dnsjinja` erfolgt.

Im Repository finden sich im Unterverzeichnis `samples` jeweils ein Beispiel für eine Datei mit Umgebungsvariablen, die von `dnsjinja` verwendet werden können und für ein Powershell-Script, dass die Nutzung vereinfacht indem die virtuelle Umgebung im Script aktiviert und deaktiviert wird.

## Benutzung

`dnsjinja` wird mit den benötigten Kommandozeilen-Parameter aufgerufen. Die Konfiguration erfolgt in
der angegebenen Konfigurationsdatei als [JSON](https://www.json.org/json-en.html) Datenstruktur.
Im Abschnitt `global` werden die lokalen Pfade für Templates
und Zone-Files sowie die URLs für den Upload und Backup per REST-API konfiguriert. Im Abschnitt `domains` werden die zu
bearbeitenden Domains mit Template-Dateien und Ausgabe-Dateien konfiguriert.

Umgebungsvariablen, die in  einer passenden `.env` definiert sind, werden berücksichtigt. Am besten werden die Variablen
in `$HOME/.dnsjinja/dnsjinja.env` gesetzt.

```
> dnsjinja --help
Usage: dnsjinja [OPTIONS]

  Modulare Verwaltung von DNS-Zonen

Options:
  -d, --datadir TEXT     Basisverzeichnis für Templates und Konfiguration
                         (DNSJINJA_DATADIR)  [default: .]
  -c, --config TEXT      Konfigurationsdatei (DNSJINJA_CONFIG)  [default:
                         config/config.json]
  -u, --upload           Upload der Zonen
  -b, --backup           Backup der Zonen
  -w, --write            Zone-Files schreiben
  --auth-api-token TEXT  AUTH-API-TOKEN für REST-API
```

Das `Auth-Token` für Backup und Upload bei Hetzner wird bei Bedarf abgefragt. Es ist sicher abzulegen, es kann
bei Hetzner nicht erneut abgefragt werden.

Eine Vorlage für eine `config.json` kann mithilfe von `explore_hetzner` aus einem existieren Hetzner-Account erstellt werden.
`explore_hetzner` wird bei der Installation mit `pip` ebenfalls erzeugt.

```
> explore_hetzner --help
Usage: explore_hetzner [OPTIONS]

  Expore Hetzner DNS Zones

Options:
  -o, --output FILENAME  Ausgabedatei für die Ergebnisse
  --auth-api-token TEXT  AUTH-API-TOKEN für REST-API (DNSJINJA_AUTH_API_TOKEN)
  --help                 Show this message and exit.
```

## Daten-Repository

`dnsjinja` trennt das Werkzeug von den Daten. Templates und Konfiguration werden in einem separaten Daten-Repository verwaltet.
Das Daten-Repository wird über die Kommandozeilenoption `--datadir` bzw. die Umgebungsvariable `DNSJINJA_DATADIR` referenziert.

Die erwartete Verzeichnisstruktur des Daten-Repositorys ist:

```
<daten-repo>/
├── config/
│   └── config.json              # Konfigurationsdatei
├── templates/
│   ├── standard.tpl             # Haupt-Template (Einstiegspunkt)
│   └── include/                 # Modulare Include-Dateien
│       ├── 00-ttl.inc           # $ORIGIN und $TTL Direktiven
│       ├── 00-meta.inc          # SOA + NS + Subdomain-Meta
│       ├── 00-subdomain-meta.inc # Provider-Includes + Custom-Records
│       ├── soa/                 # SOA-Records je DNS-Provider
│       ├── ns/                  # NS-Records je DNS-Provider
│       ├── mail/                # Mail-Konfiguration je Provider (MX, SPF, DKIM, DMARC)
│       ├── www/                 # Webserver-Konfiguration je Provider (A/AAAA)
│       ├── xmpp/                # XMPP-Konfiguration je Provider (SRV)
│       ├── custom/              # Domain-spezifische DNS-Einträge
│       ├── custom-groups/       # Gemeinsame Konfigurationen für mehrere Domains
│       └── validation/          # Domain-Validierungs-TXT-Records
├── zone-files/                  # Erzeugte Zone-Files (nicht versioniert)
└── zone-backups/                # Zone-Backups von Hetzner (nicht versioniert)
```

Im Unterverzeichnis `samples/` dieses Repositorys findet sich ein vollständiger Beispiel-Datensatz mit `config.json.sample` und einem kompletten Template-Set.

## Konfiguration

Die Konfiguration erfolgt in einer JSON-Datei mit zwei Abschnitten: `global` und `domains`.

### Abschnitt `global`

Der Abschnitt `global` definiert die Infrastruktur-Einstellungen:

| Feld | Beschreibung |
|------|-------------|
| `zone-files` | Verzeichnis für erzeugte Zone-Files |
| `zone-backups` | Verzeichnis für Zone-Backups |
| `templates` | Verzeichnis für Jinja2-Templates |
| `dns-upload-api` | URL der Hetzner Upload API (`{ZoneID}` wird ersetzt) |
| `dns-download-api` | URL der Hetzner Download API (`{ZoneID}` wird ersetzt) |
| `dns-zones-api` | URL der Hetzner Zonen API |
| `name-servers` | Liste der Nameserver-IPs für SOA-Abfragen |

### Abschnitt `domains`

Jeder Eintrag im Abschnitt `domains` definiert eine zu verwaltende Domain. Der Schlüssel ist der Domain-Name, der Wert ein Objekt mit folgenden Feldern:

| Feld | Pflicht | Typ | Beschreibung |
|------|---------|-----|-------------|
| `template` | ja | String | Jinja2-Template-Dateiname (z.B. `standard.tpl`) |
| `mail` | nein | String | Mail-Provider (wählt `include/mail/mail_<wert>.inc`) |
| `www` | nein | String | Web-Provider (wählt `include/www/www_<wert>.inc`) |
| `xmpp` | nein | String | XMPP-Provider (wählt `include/xmpp/xmpp_<wert>.inc`) |
| `registrar` | nein | String | Name des Registrars (wird als TXT-Record gespeichert) |
| `subdomains` | nein | Array | Liste der Subdomains, die als eigene Zonen verarbeitet werden |
| `custom_groups` | nein | Array | Liste gemeinsamer Konfigurationsgruppen |

Die Felder `zone-id` und `zone-file` werden automatisch durch Abgleich mit der Hetzner API befüllt.

Alle konfigurierten Felder werden als Jinja2-Variablen an die Templates übergeben.

### Beispiel

```json
{
  "global": {
    "zone-files": "zone-files",
    "zone-backups": "zone-backups",
    "templates": "templates",
    "dns-upload-api": "https://dns.hetzner.com/api/v1/zones/{ZoneID}/import",
    "dns-download-api": "https://dns.hetzner.com/api/v1/zones/{ZoneID}/export",
    "dns-zones-api": "https://dns.hetzner.com/api/v1/zones",
    "name-servers": ["213.133.100.98", "88.198.229.192", "193.47.99.5"]
  },
  "domains": {
    "example.com": {
      "template": "standard.tpl",
      "mail": "example-provider",
      "www": "example-provider",
      "xmpp": "example-provider",
      "registrar": "Hetzner",
      "subdomains": ["blog", "dev"],
      "custom_groups": ["shared-hosting"]
    },
    "example.org": {
      "template": "standard.tpl",
      "mail": "example-provider",
      "www": "example-provider",
      "registrar": "Namecheap"
    },
    "example.net": {
      "template": "standard.tpl",
      "registrar": "GoDaddy"
    }
  }
}
```

Ein vollständiges Konfigurationsbeispiel findet sich in `samples/config.json.sample`.

## Template-Architektur

Die Templates nutzen eine modulare Include-Architektur mit dynamischer Provider-Auswahl. Ein einzelnes Haupt-Template (`standard.tpl`) kann für alle Domains verwendet werden - die tatsächlich erzeugten DNS-Records werden durch die Konfiguration je Domain gesteuert.

### Rendering-Ablauf

```
standard.tpl (Einstiegspunkt je Domain)
├── include/00-ttl.inc              → $ORIGIN + $TTL
├── include/00-meta.inc             → SOA + NS + Records der Hauptdomain
│   ├── include/soa/soa_<provider>.inc      (Standard: hetzner)
│   ├── include/ns/ns_<provider>.inc        (Standard: hetzner)
│   └── include/00-subdomain-meta.inc
│       ├── include/mail/mail_<provider>.inc        (optional)
│       ├── include/xmpp/xmpp_<provider>.inc        (optional)
│       ├── include/www/www_<provider>.inc           (optional)
│       ├── include/custom/<domain>.inc              (optional)
│       └── include/custom-groups/<gruppe>.inc       (je Gruppe, optional)
└── Für jede Subdomain:
    ├── include/00-ttl.inc          → $ORIGIN für <sub>.<domain>
    └── include/00-subdomain-meta.inc → gleiche Provider-Includes für Subdomain
```

### Dynamische Provider-Auswahl

Die Include-Dateinamen werden dynamisch aus den Konfigurationswerten zusammengesetzt. Beispiel:

```jinja2
{% set include_mail = 'include/mail/mail_' + mail|default('none') + '.inc' %}
{% include include_mail ignore missing %}
```

Ist `"mail": "example-provider"` in der Konfiguration gesetzt, wird `include/mail/mail_example-provider.inc` eingebunden. Fehlt das Feld `mail`, wird `mail_none.inc` gesucht - existiert diese Datei nicht, wird sie durch `ignore missing` stillschweigend übersprungen.

Dieses Prinzip gilt für alle Provider-Kategorien: `mail`, `www`, `xmpp`, `soa` und `ns`.

### Subdomain-Verarbeitung

Subdomains werden in einer Schleife verarbeitet. Dabei wird die Variable `domain` auf den vollqualifizierten Subdomain-Namen gesetzt (z.B. `blog.example.com`). Die gleichen Include-Dateien werden sowohl für Hauptdomains als auch für Subdomains verwendet:

```jinja2
{% set org_domain = domain %}
{% for dom in subdomains %}
{% set domain = dom + '.' + org_domain %}
{% include 'include/00-subdomain-meta.inc' %}
{% endfor %}
```

Domain-spezifische Custom-Records für Subdomains können in `include/custom/<subdomain>.<domain>.inc` angelegt werden (z.B. `include/custom/blog.example.com.inc`).

### Custom-Records und Shared Groups

**Domain-spezifische Records:** Für jede Domain kann eine eigene Include-Datei `include/custom/<domain>.inc` angelegt werden. Diese wird automatisch eingebunden, wenn sie existiert - es ist keine Änderung an der Konfiguration nötig.

**Shared Groups:** Konfigurationen, die von mehreren Domains gemeinsam genutzt werden, können in `include/custom-groups/<name>.inc` definiert werden. In der Konfiguration werden sie per `"custom_groups": ["<name>"]` referenziert.

**Validierungs-Records:** Domain-Ownership-Verifizierungen (z.B. für Mail-Provider) werden in `include/validation/<domain>.inc` gespeichert und typischerweise aus den Mail-Provider-Includes heraus eingebunden.

### Jinja2-Variablen in Templates

| Variable | Quelle | Beschreibung |
|----------|--------|-------------|
| `domain` | automatisch | Aktuell verarbeitete Domain (wird für Subdomains überschrieben) |
| `soa_serial` | automatisch | SOA-Seriennummer im Format `JJJJMMTT##` |
| `mail` | Konfiguration | Mail-Provider-Auswahl |
| `www` | Konfiguration | Web-Provider-Auswahl |
| `xmpp` | Konfiguration | XMPP-Provider-Auswahl |
| `registrar` | Konfiguration | Registrar-Name für TXT-Record |
| `subdomains` | Konfiguration | Liste der zu verarbeitenden Subdomains |
| `custom_groups` | Konfiguration | Liste der einzubindenden Shared Groups |

### Eigener Jinja2-Filter: `hostname`

In Templates steht der Filter `hostname` zur Verfügung, der einen Hostnamen in eine IPv4-Adresse auflöst:

```jinja2
server  IN  A  {{ "mail.example.com" | hostname }}
```

### Neuen Provider hinzufügen

1. Neue Include-Datei anlegen: `include/<kategorie>/<kategorie>_<name>.inc` (z.B. `include/mail/mail_neuer-provider.inc`)
2. In der Domain-Konfiguration referenzieren: `"mail": "neuer-provider"`

## Beispielkonfiguration

Im Unterverzeichnis `samples/` findet sich ein vollständiger Beispiel-Datensatz:

- `samples/config.json.sample` - Beispiel-Konfiguration mit mehreren Domain-Varianten
- `samples/templates/` - Vollständiges Template-Set mit allen Include-Kategorien

Die Beispiele verwenden ausschließlich abstrakte Daten (`example.com`, `198.51.100.x` etc.) und können als Ausgangspunkt für eine eigene Konfiguration dienen.

## GitHub Actions

`dnsjinja` kann über GitHub Actions automatisiert werden. Dabei wird ein Workflow im Daten-Repository eingerichtet, der bei jedem Push auf `main` die DNS-Zonen erzeugt und bei Hetzner einspielt:

1. `dnsjinja` wird aus dem Tool-Repository installiert
2. Das Daten-Repository wird ausgecheckt
3. `dnsjinja -b -w -u` wird ausgeführt (Backup, Write, Upload)
4. Zone-Files und Zone-Backups werden als Build-Artefakte gespeichert
5. Der Exit-Status wird über `exit_on_error` geprüft

Benötigte GitHub Secrets und Variables:
- `HETZNER_API_AUTH_TOKEN` (Secret) - API-Token für Hetzner
- `GH_PAT_DNSJINJA` (Secret) - GitHub PAT für Installation von dnsjinja aus privatem Repository
- `DNSJINJA` (Variable) - Repository-Pfad des dnsjinja-Tools
- `DNSDATA` (Variable) - Repository-Pfad der DNS-Daten
