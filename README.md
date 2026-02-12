# DNSJinja zum Erstellen von Bind9-Zone-Files

`dnsjinja` ist ein Python-Script, das mit Hilfe von [Jinja](https://palletsprojects.com/p/jinja/) aus modularen
Template-Dateien Bind9-kompatible Zone-Filers erzeugt.

Diese Zone-Files sollten genutzt werden, um die DNS-Konfiguration per [Hetzner Cloud API](https://docs.hetzner.cloud/) bei Hetzner einzuspielen.

## Migration auf die Hetzner Cloud API

Ab Version 0.3.0 nutzt `dnsjinja` die neue [Hetzner Cloud API](https://docs.hetzner.cloud/) (`api.hetzner.cloud/v1`)
anstelle der alten DNS API (`dns.hetzner.com/api/v1`), die im Mai 2026 abgeschaltet wird.

### Wichtige Änderungen bei der Migration

- **Neuer API-Token erforderlich**: Tokens der alten DNS API funktionieren nicht mit der neuen Cloud API.
  Ein neuer API-Token muss in der [Hetzner Cloud Console](https://console.hetzner.cloud/) erstellt werden.
- **Authentifizierung**: Statt `Auth-API-Token` Header wird nun `Authorization: Bearer <token>` verwendet.
- **Konfiguration vereinfacht**: Die drei separaten API-URLs (`dns-upload-api`, `dns-download-api`, `dns-zones-api`)
  werden durch eine einzige optionale `dns-api-base` URL ersetzt (Standard: `https://api.hetzner.cloud/v1`).
- **`zone-id` in Domains nicht mehr erforderlich**: Die Zone-ID wird automatisch von der API ermittelt.

### Beispiel config.json (neu)

```json
{
  "global": {
    "templates": "templates",
    "zone-files": "zone-files",
    "zone-backups": "zone-backups",
    "name-servers": ["213.133.100.98", "88.198.229.192", "193.47.99.5"]
  },
  "domains": {
    "example.com": {
      "template": "example.com.tpl"
    }
  }
}
```

Das Feld `dns-api-base` kann optional angegeben werden, um eine andere API-Basis-URL zu nutzen.

## Installation

`dnsjinja` kann mit einem aktuellen Python genutzt werden bei dem die Module aus `requirements.txt` installiert sind.
Es ist empfohlen, dafür eine [virtuelle Python Umgebung](https://realpython.com/python-virtual-environments-a-primer/) zu nutzen. Bei der Installation von `dnsjinja` mit `pip` werden alle benötigten Abhängigkeiten installiert.

Nach Aktivierung der virtuellen Python Umgebung sollte `dnsjinja` dort aus github mit
` pip install git+ssh://git@github.com/kaijen/dnsjinja.git` oder `pip install git+https://github.com/kaijen/dnsjinja.git` installiert werden.

Dabei wird innerhalb der virtuellen Umgebung eine ausführbare Datei erzeugt, über die die Verwaltung der Domänen auf der Kommandozeile mit `dnsjinja` erfolgt.

Im Repository finden sich im Unterverzeichnis `samples` jeweils ein Beispiel für eine Datei mit Umgebungsvariablen, die von `dnjsinja` verwendet werden können und für ein Powershell-Script, dass die Nutzung vereinfacht indem die virtuelle Umgebung im Script aktiviert und deaktiviert wird.

## Benutzung

`dnsjinja` wird mit den benötigten Kommandozeilen-Parameter aufgerufen. Die Konfiguration erfolgt in
der angegebenen Konfigurationsdatei als [JSON](https://www.json.org/json-en.html) Datenstruktur.
Im Abschnitt `global` werden die lokalen Pfade für Templates
und Zone-Files sowie optional die Basis-URL der Hetzner Cloud API konfiguriert. Im Abschnitt `domains` werden die zu
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
```

Das API-Token für Backup und Upload bei Hetzner wird bei Bedarf abgefragt. Es muss in der
[Hetzner Cloud Console](https://console.hetzner.cloud/) erstellt und sicher abgelegt werden.

Eine Vorlage für eine `config.json` kann mithilfe von `explore_hetzner` aus einem existieren Hetzner-Account erstellt werden.
`explore_hetzner` wird bei der Installation mit `pip` ebenfalls erzeugt.

```
> explore_hetzner --help
Usage: explore_hetzner [OPTIONS]

  Explore Hetzner DNS Zones (Cloud API)

Options:
  -o, --output FILENAME  Ausgabedatei für die Ergebnisse
  --auth-api-token TEXT  API-Token (Bearer) für Hetzner Cloud API (DNSJINJA_AUTH_API_TOKEN)
  --api-base TEXT        Basis-URL der Hetzner Cloud API (DNSJINJA_API_BASE)
  --help                 Show this message and exit.
```
