# DNS-Backends

Welchen DNS-Anbieter `dnsjinja` anspricht, entscheidet `global.dns-backend` in der
`config.json`. Mitgeliefert sind zwei Backends:

```json
{
  "global": {
    "dns-backend": "desec"
  }
}
```

Ohne Angabe gilt `hetzner` – bestehende Konfigurationen ändern ihr Verhalten also nicht.

!!! warning "Backend ist nicht Provider"
    Das Wort *Provider* bezeichnet in diesem Projekt die Service-Provider auf
    Template-Ebene: `mail`, `www`, `xmpp`, `ns` und `soa` wählen die Includes unter
    `include/<kategorie>/`. Das **Backend** ist etwas anderes: die API, über die
    hochgeladen wird. Beides ist unabhängig voneinander konfigurierbar.

## Welche Backends verfügbar sind

```console
$ explore_dns --list-backends
desec (builtin)
hetzner (builtin)
```

## Fähigkeiten im Vergleich

| | Hetzner | deSEC |
|---|---|---|
| Adressierung der Zone | numerische ID | Domainname |
| Mindest-TTL | 60 | 3600 (frei), pro Domain über `minimum_ttl` |
| Höchst-TTL | keine | 86400 |
| Änderungen schreiben | eine Aktion je RRSet | ein atomarer Sammelaufruf |
| Teilweise angewandte Änderung möglich | ja | nein |
| Vom Anbieter verwaltet | SOA | SOA, DNSKEY, DS, CDS, CDNSKEY, RRSIG, NSEC* |
| RRSet-Schutzflag | ja | nein (stattdessen Token-Policies) |
| Zonefile exportieren | ja | ja |
| Zonefile in bestehende Zone importieren | ja | nein |
| DNSSEC | Zone selbst verwalten | automatisch signiert |

## Token

Das Token kommt aus – in dieser Reihenfolge:

1. `--auth-api-token`
2. `DNSJINJA_<BACKEND>_AUTH_API_TOKEN`, also `DNSJINJA_HETZNER_AUTH_API_TOKEN` bzw.
   `DNSJINJA_DESEC_AUTH_API_TOKEN`
3. `DNSJINJA_AUTH_API_TOKEN`

Wer beide Anbieter parallel betreibt, hinterlegt die backendspezifischen Variablen in
einer `.env` und braucht die allgemeine nicht mehr.

## Basis-URL

Jedes Backend bringt seine eigene Standard-URL mit (`https://api.hetzner.cloud/v1` bzw.
`https://desec.io/api/v1`). `global.dns-api-base` überschreibt sie, etwa für eine
eigene Installation.

## TTL-Grenzen

Die Templates setzen `$TTL 300`. Das liegt unter der Mindest-TTL von deSEC. `dnsjinja`
hebt zu niedrige TTLs vor dem Vergleich an und schreibt eine Warnung; zu hohe werden
gekappt. Die Anpassung passiert **vor** dem Soll-Ist-Vergleich, damit
`--dry-run-compare` und der Upload dieselben Daten sehen – sonst zeigte der
Trockenlauf 300, hochgeladen würde 3600, und beim nächsten Lauf erschiene derselbe
Unterschied erneut.

## Eigene Backends anschließen

Ein fremdes Paket meldet ein Backend über die Entry-Point-Gruppe `dnsjinja.backends`:

```toml
[project.entry-points."dnsjinja.backends"]
meinanbieter = "meinpaket.backend:MeinBackend"
```

Die Klasse erbt von `dnsjinja.backends.DNSBackend` und implementiert fünf Methoden:
`list_zones()`, `create_zone()`, `export_zonefile()`, `list_rrsets()` und
`apply_changes()`. Dazu kommt ein `BackendCapabilities`-Objekt mit den Grenzen des
Anbieters.

`apply_changes()` bekommt den **kompletten** Änderungsplan, nicht einzelne Records.
Genau deshalb passen beide Anbieter unter dieselbe Schnittstelle: Hetzner macht daraus
Einzelaktionen, deSEC einen Sammelaufruf.

Nach der Installation steht der Name in `global.dns-backend` zur Verfügung. Die
`config.json` nennt ausschließlich Namen – ein Modulpfad wird bewusst nicht akzeptiert,
sonst entschiede eine Konfigurationsdatei darüber, welcher Code ausgeführt wird. Ein
Plugin, das sich nicht laden lässt, wird protokolliert und übersprungen; die übrigen
Backends bleiben benutzbar.
