# DNSJinja zum Erstellen von Bind9-Zone-Files

`dnsjinja` ist ein Python-Script, das mit Hilfe von [Jinja](https://palletsprojects.com/p/jinja/) aus modularen
Template-Dateien Bind9-kompatible Zone-Files erzeugt.

Diese Zone-Files sollten genutzt werden, um die DNS-Konfiguration per [Hetzner Cloud API](https://docs.hetzner.cloud/reference/cloud#tag/zone-actions) bei Hetzner einzuspielen.

## Installation

`dnsjinja` kann mit einem aktuellen Python genutzt werden bei dem die Module aus `requirements.txt` installiert sind.
Es ist empfohlen, dafür eine [virtuelle Python Umgebung](https://realpython.com/python-virtual-environments-a-primer/) zu nutzen. Bei der Installation von `dnsjinja` mit `pip` werden alle benötigten Abhängigkeiten installiert.

Nach Aktivierung der virtuellen Python Umgebung sollte `dnsjinja` dort aus github mit
`pip install git+ssh://git@github.com/kaijen/dnsjinja.git` oder `pip install git+https://github.com/kaijen/dnsjinja.git` installiert werden.

Dabei wird innerhalb der virtuellen Umgebung eine ausführbare Datei erzeugt, über die die Verwaltung der Domänen auf der Kommandozeile mit `dnsjinja` erfolgt.

Im Repository finden sich im Unterverzeichnis `samples` jeweils ein Beispiel für eine Datei mit Umgebungsvariablen, die von `dnsjinja` verwendet werden können und für ein Powershell-Script, dass die Nutzung vereinfacht indem die virtuelle Umgebung im Script aktiviert und deaktiviert wird.

### Virtuelle Python-Umgebung

Einrichtung einer virtuellen Umgebung:

```bash
python -m venv .venv
```

Aktivierung:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Installation von `dnsjinja` in der aktivierten Umgebung:

```bash
pip install git+ssh://git@github.com/kaijen/dnsjinja.git
```

Anschließend stehen die Kommandos `dnsjinja`, `explore_hetzner` und `exit_on_error` zur Verfügung.

Die Umgebungsvariablen können in `$HOME/.dnsjinja/dnsjinja.env` konfiguriert werden (siehe `samples/dnsjinja.env.sample`). Ein Beispiel für ein PowerShell-Wrapper-Script findet sich in `samples/dnsjinja.ps1.sample`.

### Docker

`dnsjinja` kann alternativ über Docker ausgeführt werden. Das Dockerfile nutzt ein Multi-Stage-Build mit zwei Targets:

- **`prod`** - Produktions-Container mit installiertem `dnsjinja`
- **`dev`** - Entwicklungs-Container mit `pip install -e .` (editierbare Installation)

#### Mit docker-compose

Das Daten-Repository (Templates, Config, Zone-Files) wird als Volume eingebunden. Die Umgebungsvariable `DNSJINJA_DATADIR` muss auf dem Host auf das Daten-Repository zeigen:

```bash
# Backup, Write und Upload ausführen
DNSJINJA_AUTH_API_TOKEN=<token> DNSJINJA_DATADIR=/pfad/zum/daten-repo \
  docker compose run --rm dnsjinja -b -w -u

# Entwicklungs-Container (Source-Code wird live gemountet)
DNSJINJA_AUTH_API_TOKEN=<token> DNSJINJA_DATADIR=/pfad/zum/daten-repo \
  docker compose run --rm dnsjinja-dev -b -w -u
```

#### Mit docker build/run

```bash
# Image bauen (Produktion)
docker build --target prod -t dnsjinja .

# Image bauen (Entwicklung)
docker build --target dev -t dnsjinja-dev .

# Ausführen mit Volume-Mount
docker run --rm \
  -v /pfad/zum/daten-repo:/data \
  -e DNSJINJA_AUTH_API_TOKEN=<token> \
  -e DNSJINJA_DATADIR=/data \
  -e DNSJINJA_CONFIG=/data/config/config.json \
  dnsjinja -b -w -u
```

#### explore_hetzner im Container

Da der ENTRYPOINT auf `dnsjinja` gesetzt ist, kann `explore_hetzner` über `--entrypoint` aufgerufen werden:

```bash
docker compose run --rm --entrypoint explore_hetzner dnsjinja --auth-api-token <token>
```

#### PowerShell-Funktionen für `$PROFILE`

Die folgenden Funktionen kapseln die Docker-Aufrufe und können in das PowerShell-Profil (`$PROFILE`) eingebunden werden. Die Umgebungsvariablen `DNSJINJA_AUTH_API_TOKEN` und `DNSJINJA_DATADIR` müssen gesetzt sein (z.B. über `$HOME/.dnsjinja/dnsjinja.env` oder direkt in `$PROFILE`).

```powershell
# Pfad zum DNSJinja-Repository (anpassen, falls nicht als Umgebungsvariable gesetzt)
if (-not $env:DNSJINJA_COMPOSE) { $env:DNSJINJA_COMPOSE = "D:\github-kaijen\DNSJinja" }

function Invoke-DNSJinja {
    <#
    .SYNOPSIS
        Führt dnsjinja im Docker-Container aus.
    .EXAMPLE
        Invoke-DNSJinja -b -w -u
        Invoke-DNSJinja --backup --write
    #>
    docker compose -f "$env:DNSJINJA_COMPOSE\docker-compose.yml" run --rm dnsjinja @args
}

function Invoke-DNSJinjaDev {
    <#
    .SYNOPSIS
        Führt dnsjinja im Entwicklungs-Container aus (Source live gemountet).
    .EXAMPLE
        Invoke-DNSJinjaDev -b -w -u
    #>
    docker compose -f "$env:DNSJINJA_COMPOSE\docker-compose.yml" run --rm dnsjinja-dev @args
}

function Invoke-ExploreHetzner {
    <#
    .SYNOPSIS
        Führt explore_hetzner im Docker-Container aus.
    .EXAMPLE
        Invoke-ExploreHetzner -o config.json
    #>
    docker compose -f "$env:DNSJINJA_COMPOSE\docker-compose.yml" run --rm --entrypoint explore_hetzner dnsjinja @args
}

Set-Alias -Name dnsjinja -Value Invoke-DNSJinja
Set-Alias -Name dnsjinja-dev -Value Invoke-DNSJinjaDev
Set-Alias -Name explore-hetzner -Value Invoke-ExploreHetzner
```

Damit lässt sich `dnsjinja` direkt auf der Kommandozeile nutzen:

```powershell
dnsjinja -b -w -u
explore-hetzner -o config.json
```

## Benutzung

`dnsjinja` wird mit den benötigten Kommandozeilen-Parameter aufgerufen. Die Konfiguration erfolgt in
der angegebenen Konfigurationsdatei als [JSON](https://www.json.org/json-en.html) Datenstruktur.
Im Abschnitt `global` werden die lokalen Pfade für Templates
und Zone-Files konfiguriert. Im Abschnitt `domains` werden die zu
bearbeitenden Domains mit Template-Dateien und Ausgabe-Dateien konfiguriert.

Umgebungsvariablen, die in  einer passenden `.env` definiert sind, werden berücksichtigt. Am besten werden die Variablen
in `$HOME/.dnsjinja/dnsjinja.env` gesetzt.

```
> dnsjinja --help
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
  --auth-api-token TEXT  API-Token (Bearer) für Hetzner Cloud API
                         (DNSJINJA_AUTH_API_TOKEN)
```

Das API-Token (Bearer) wird in der [Hetzner Cloud Console](https://console.hetzner.cloud/) im jeweiligen Projekt erstellt.
Alte `Auth-API-Token` von `dns.hetzner.com` funktionieren nicht mehr.
Das Token wird bei Bedarf abgefragt und ist sicher abzulegen.

Eine Vorlage für eine `config.json` kann mithilfe von `explore_hetzner` aus einem existieren Hetzner-Account erstellt werden.
`explore_hetzner` wird bei der Installation mit `pip` ebenfalls erzeugt.

```
> explore_hetzner --help
Usage: explore_hetzner [OPTIONS]

  Explore Hetzner DNS Zones (Cloud API)

Options:
  -o, --output FILENAME  Ausgabedatei für die Ergebnisse
  --auth-api-token TEXT  API-Token (Bearer) für Hetzner Cloud API
                         (DNSJINJA_AUTH_API_TOKEN)
  --api-base TEXT        Basis-URL der Hetzner Cloud API (DNSJINJA_API_BASE)
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

| Feld | Pflicht | Beschreibung |
|------|---------|-------------|
| `zone-files` | ja | Verzeichnis für erzeugte Zone-Files |
| `zone-backups` | ja | Verzeichnis für Zone-Backups |
| `templates` | ja | Verzeichnis für Jinja2-Templates |
| `name-servers` | ja | Liste der Nameserver-IPs für SOA-Abfragen |
| `dns-api-base` | nein | Basis-URL der Hetzner Cloud API (Standard: `https://api.hetzner.cloud/v1`) |

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

Die Felder `zone-id` und `zone-file` werden automatisch durch Abgleich mit der Hetzner Cloud API befüllt.

Alle konfigurierten Felder werden als Jinja2-Variablen an die Templates übergeben.

### Beispiel

```json
{
  "global": {
    "zone-files": "zone-files",
    "zone-backups": "zone-backups",
    "templates": "templates",
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

## Hetzner Cloud API

`dnsjinja` nutzt die [Hetzner Cloud API](https://docs.hetzner.cloud/reference/cloud#tag/zone-actions) mit Bearer-Token-Authentifizierung. Die API-Implementierung orientiert sich an der offiziellen Python-Bibliothek [hcloud-python](https://github.com/hetznercloud/hcloud-python). Die Basis-URL (`https://api.hetzner.cloud/v1`) kann über `dns-api-base` in der Konfiguration oder die Umgebungsvariable `DNSJINJA_API_BASE` überschrieben werden.

Verwendete Endpunkte:

| Endpunkt | Methode | Beschreibung |
|----------|---------|--------------|
| `{dns-api-base}/zones` | GET | Zonen auflisten (paginiert, 100 pro Seite) |
| `{dns-api-base}/zones/{zone-id}/actions/import_zonefile` | POST | Zone-File importieren (Upload) |
| `{dns-api-base}/zones/{zone-id}/zonefile` | GET | Zone-File exportieren (Backup) |

Die Authentifizierung erfolgt über den HTTP-Header `Authorization: Bearer {token}`. Der Token wird über die Hetzner Cloud Console erstellt (nicht der alte Auth-API-Token von dns.hetzner.com).

## GitHub Actions

`dnsjinja` kann über GitHub Actions automatisiert werden. Dabei wird ein Workflow im Daten-Repository eingerichtet, der bei jedem Push auf `main` die DNS-Zonen erzeugt und über die Hetzner Cloud API einspielt:

1. `dnsjinja` wird aus dem Tool-Repository installiert
2. Das Daten-Repository wird ausgecheckt
3. `dnsjinja -b -w -u` wird ausgeführt (Backup, Write, Upload)
4. Zone-Files und Zone-Backups werden als Build-Artefakte gespeichert
5. Der Exit-Status wird über `exit_on_error` geprüft

Benötigte GitHub Secrets und Variables:
- `HETZNER_API_AUTH_TOKEN` (Secret) - Bearer-Token aus Hetzner Cloud Console
- `GH_PAT_DNSJINJA` (Secret) - GitHub PAT für Installation von dnsjinja aus privatem Repository
- `DNSJINJA` (Variable) - Repository-Pfad des dnsjinja-Tools
- `DNSDATA` (Variable) - Repository-Pfad der DNS-Daten
