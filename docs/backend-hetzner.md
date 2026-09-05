# Hetzner Cloud

Backend-Name: `hetzner` (Standard). Standard-URL: `https://api.hetzner.cloud/v1`.

`dnsjinja` kommuniziert über die offizielle Python-Bibliothek
[hcloud-python](https://github.com/hetznercloud/hcloud-python) mit der
[Hetzner Cloud API](https://docs.hetzner.cloud/reference/cloud#tag/zone-actions).
HTTP-Aufrufe, Authentifizierung und Paginierung übernimmt die Bibliothek.

## Token erstellen

Das Bearer-Token wird in der [Hetzner Cloud Console](https://console.hetzner.cloud/)
erstellt: **Projekt → Security → API Tokens → Generate API Token** mit
**Read & Write**.

!!! danger "Kein alter DNS-Token"
    Es muss ein **Cloud-API-Token** sein. Die früheren `Auth-API-Token` aus der
    DNS-Konsole (`dns.hetzner.com`) funktionieren mit der Cloud API **nicht** und
    führen zu Authentifizierungsfehlern.

Das Token wird über `--auth-api-token`, `DNSJINJA_HETZNER_AUTH_API_TOKEN`,
`DNSJINJA_AUTH_API_TOKEN` oder eine `.env`-Datei bereitgestellt.

## Basis-URL überschreiben

Standardmäßig spricht `dnsjinja` `https://api.hetzner.cloud/v1` an. Die Basis-URL lässt
sich überschreiben:

- in der `config.json` über `global.dns-api-base`
- für `explore_dns` über `--api-base` bzw. `DNSJINJA_API_BASE`

## Verwendete Operationen

Die Aufrufe stecken im Backend `dnsjinja.backends.hetzner`; der Kern von `dnsjinja`
kennt sie nicht.

| Operation | hcloud-Methode | Verwendet für |
|-----------|----------------|---------------|
| Zonen auflisten | `client.zones.get_all()` | Abgleich Config ↔ Hetzner, Zonen-IDs |
| Zone neu anlegen | `client.zones.create(name, mode="primary")` | `--create-missing` |
| Zone exportieren | `client.zones.export_zonefile(zone)` | Backup (`-b`) |
| RRSets lesen | `client.zones.get_rrset_all(zone)` | Soll-/Ist-Abgleich beim Upload |
| RRSet anlegen/ändern | `client.zones.create_rrset(...)` / `set_rrset_records(...)` | Upload (`-u`) |
| RRSet löschen | `client.zones.delete_rrset(rrset)` | Upload (`-u`), veraltete Records |
| TTL ändern | `client.zones.change_rrset_ttl(...)` | Upload (`-u`) |
| Zone importieren | `client.zones.import_zonefile(zone, zonefile)` | Restore aus Backup |

## So funktioniert der Upload (RRSet-Sync)

Der Upload arbeitet auf Record-Ebene und macht die Hetzner-Zone deckungsgleich mit dem
gerenderten Template. Anders als bei deSEC gibt es keinen Sammelaufruf: Bricht der Lauf
in der Mitte ab, sind die vorherigen Änderungen bereits wirksam.

1. **Rendern & validieren** – das Zone-File wird gerendert und mit dnspython auf
   Syntax geprüft. Fehler brechen den Lauf für diese Domain ab.
2. **Soll-Ist-Abgleich** – gerenderte RRSets werden mit den vorhandenen verglichen.
3. **Anlegen / Aktualisieren** – neue RRSets werden erstellt, geänderte aktualisiert.
4. **Löschen** – RRSets, die nicht (mehr) im Template stehen, werden entfernt.

Ausgenommen sind der SOA-Record (von Hetzner verwaltet) sowie als *protected*
markierte RRSets, die übersprungen werden.

!!! tip "Restore aus dem Backup"
    Jeder Lauf mit `-b` legt vor Änderungen ein Zonefile in `zone-backups/` ab. Im
    Notfall lässt sich eine Zone daraus mit `client.zones.import_zonefile(zone,
    zonefile)` vollständig wiederherstellen (ersetzt alle RRSets der Zone).

## Grenzen

- Mindest-TTL 60 Sekunden, keine Obergrenze.
- Vom Anbieter verwaltet ist nur der SOA-Record.
- RRSets können ein Schutzflag (`protection.change`) tragen; solche RRSets überspringt
  der Upload mit einer Warnung und zeigt sie im Vergleich als `!` an.
- Die Anwendung eines Änderungsplans ist **nicht** atomar.
