# Konfiguration

Die gesamte Konfiguration steht in einer JSON-Datei (Standard:
`config/config.json`) mit zwei Abschnitten: `global` und `domains`.

## Abschnitt `global`

Infrastruktur-Einstellungen, die für alle Domains gelten:

| Feld | Pflicht | Beschreibung |
|------|---------|-------------|
| `zone-files` | ja | Verzeichnis für erzeugte Zone-Files |
| `zone-backups` | ja | Verzeichnis für Zone-Backups |
| `templates` | ja | Verzeichnis der Jinja2-Templates |
| `name-servers` | ja | Liste von Nameserver-IPs für die SOA-Seriennummern-Abfrage |
| `dns-api-base` | nein | Basis-URL der Hetzner Cloud API (Standard: `https://api.hetzner.cloud/v1`) |

Pfade werden relativ zum `--datadir` aufgelöst. Die `name-servers` werden benutzt, um
die aktuelle SOA-Seriennummer einer Zone zu ermitteln und hochzuzählen.

Antwortet keiner der Nameserver – etwa bei einer mit `--create-missing` frisch
angelegten Domäne, die noch nicht registriert bzw. delegiert ist – gibt dnsjinja eine
Warnung aus und startet die Seriennummer bei `JJJJMMTT01`. Der Lauf bricht deswegen
nicht ab; die SOA-Seriennummer verwaltet ohnehin Hetzner selbst, dnsjinja lädt sie
nicht hoch.

## Abschnitt `domains`

Jeder Schlüssel ist ein Domain-Name, der Wert ein Objekt:

| Feld | Pflicht | Typ | Beschreibung |
|------|---------|-----|-------------|
| `template` | ja | String | Template-Dateiname, z. B. `standard.tpl` |
| `mail` | nein | String | Mail-Provider → bindet `include/mail/mail_<wert>.inc` ein |
| `www` | nein | String | Web-Provider → bindet `include/www/www_<wert>.inc` ein |
| `xmpp` | nein | String | XMPP-Provider → bindet `include/xmpp/xmpp_<wert>.inc` ein |
| `registrar` | nein | String | Registrar-Name, wird als TXT-Record `registrar` am Zonen-Apex abgelegt (nicht bei Subdomains) |
| `subdomains` | nein | Array | Subdomains, die als eigene Zonen-Abschnitte verarbeitet werden |
| `custom_groups` | nein | Array | gemeinsame Konfigurationsgruppen |
| `ns` | nein | String | NS-Provider-Override → `include/ns/ns_<wert>.inc` (Standard: `hetzner`) |
| `soa` | nein | String | SOA-Provider-Override → `include/soa/soa_<wert>.inc` (Standard: `hetzner`) |

Alle konfigurierten Felder werden zusätzlich als Jinja2-Variablen an die Templates
übergeben und sind dort direkt verwendbar.

!!! note "Automatisch befüllte Felder"
    Die Felder `zone-id` und `zone-file` werden zur Laufzeit durch Abgleich mit der
    Hetzner Cloud API gesetzt – sie gehören **nicht** in die `config.json`.

## Beispiel

Aus [`samples/config.json.sample`](https://github.com/kaijen/dnsjinja/blob/main/samples/config.json.sample),
das die wichtigsten Varianten abdeckt:

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

Diese drei Domains zeigen das Spektrum:

- **`example.com`** – volle Ausstattung: Mail, Web, XMPP, eigene Custom-Records,
  eine geteilte Gruppe und zwei Subdomains.
- **`example.org`** – Mail und Web, sonst Standard.
- **`example.net`** – „geparkte" Domain: nur SOA, NS und der `registrar`-TXT-Record.

Wie aus diesen Einträgen konkrete Zone-Files werden, zeigt das
[vollständige Beispiel](beispiel.md).

## Validierung

`dnsjinja` validiert die `config.json` beim Start gegen ein
[pydantic](https://docs.pydantic.dev/)-Schema. `global` und `domains` sind Pflicht,
jeder Domain-Eintrag braucht mindestens ein `template`. Zusätzliche, unbekannte Felder
sind erlaubt (`extra = allow`) und werden als Template-Variablen durchgereicht – ein
Tippfehler im Feldnamen führt also nicht zum Abbruch, sondern lediglich dazu, dass das
betreffende Feld ignoriert bzw. nur als Variable verfügbar ist.
