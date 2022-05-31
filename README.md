# DNSJinja zum Erstellen von Bind9-Zone-Files

`dnsjinja` ist ein Python-Script, das mit Hilfe von [Jinja](https://palletsprojects.com/p/jinja/) aus modularen 
Template-Dateien Bind9-kompatible Zone-Filers erzeugt. 

Diese Zone-Files sollten genutzt werden, um die DNS-Konfiguration per [Hetzner REST API](https://dns.hetzner.com/api-docs) bei Hetzner einzuspielen.

## Installation

`dnsjina` kann mit einem aktuellen Python genutzt werden bei dem die Module aus `requirements.txt` installiert sind.
Es ist empfohlen, dafür eine [virtuelle Python Umgebung](https://realpython.com/python-virtual-environments-a-primer/) zu nutzen. Bei der Installation von `dnsjinja` mit `pip` werden alle benötigten Abhängigkeiten installiert.

Nach Aktivierung der virtuellen Python Umgebung sollte `dnsjinja` dort aus github mit
` pip install git+ssh://git@github.com:kaijen/dnsjinja.git` oder `pip install git+https://github.com/kaijen/dnsjinja.git` installiert werden. 

Dabei wird innerhalb der virtuellen Umgebung eine ausführbare Datei erzeugt, über die die Verwaltung der Domänen auf der Kommandozeile mit `dnsjinja` erfolgt.

Im Repository finden sich im Unterverzeichnis `samples` jeweils ein Beispiel für eine Datei mit Umgebungsvariablen, die von `dnjsinja` verwendet werden können und für ein Powershell-Script, dass die Nutzung vereinfacht indem die virtuelle Umgebung im Script aktiviert und deaktiviert wird.

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
