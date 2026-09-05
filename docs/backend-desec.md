# deSEC

Backend-Name: `desec`. Standard-URL: `https://desec.io/api/v1`.

```json
{
  "global": {
    "dns-backend": "desec"
  }
}
```

## Token erstellen

Im deSEC-Konto unter **Token Management** ein Token anlegen. Es wird als
`Authorization: Token <secret>` gesendet – nicht als Bearer-Token.

Bereitgestellt wird es über `--auth-api-token`, `DNSJINJA_DESEC_AUTH_API_TOKEN` oder
`DNSJINJA_AUTH_API_TOKEN`.

!!! tip "Token einschränken"
    deSEC kennt Token Policies: Ein Token lässt sich auf einzelne Domains, Subnames und
    Record-Typen begrenzen, und `perm_create_domain` bzw. `perm_delete_domain` steuern
    das Anlegen und Löschen von Domains getrennt. Für einen Automatisierungslauf ist ein
    eingeschränktes Token die sichere Wahl. Ein Schutzflag am einzelnen RRSet, wie
    Hetzner es kennt, gibt es dafür nicht.

## Was dieses Backend anders macht

**Ein Aufruf pro Zone.** Der komplette Änderungsplan geht als ein `PATCH` auf
`/domains/{name}/rrsets/` – atomar, alles oder nichts. Gelöscht wird über eine leere
Werteliste im selben Aufruf. Ein halb aktualisierter Zustand kann nicht entstehen.

**TTL-Grenzen.** Mindestens 3600 Sekunden bei kostenlosen Konten (die Domain meldet ihren
Wert über `minimum_ttl`), höchstens 86400. Die Templates setzen `$TTL 300`; `dnsjinja`
hebt das vor dem Vergleich an und warnt.

**DNSSEC läuft von selbst.** deSEC signiert jede Zone und stellt die DS-Records für den
Registrar bereit. SOA, DNSKEY, DS, CDS, CDNSKEY, RRSIG und die NSEC-Typen sind
schreibgeschützt und werden auf beiden Seiten des Vergleichs ausgefiltert.

**Eigene Nameserver am Apex.** deSEC verwaltet die NS-Records der Zone selbst. In der
Domain-Konfiguration gehören deshalb `"ns": "desec"` und `"soa": "desec"`, sonst rendern
die Templates Hetzner-Nameserver in eine deSEC-Zone.

**Ratenlimits.** 2 Änderungen pro Sekunde, 15 pro Minute, 100 pro Stunde und 300 pro Tag
– je Domain. `dnsjinja` beachtet `Retry-After` bei einem 429 und wiederholt begrenzt;
über `backend-options` lässt sich das anpassen:

```json
{
  "global": {
    "dns-backend": "desec",
    "backend-options": { "rate-limit-retries": 5, "timeout": 60 }
  }
}
```

## Verwendete Endpunkte

| Operation | Endpunkt | Verwendet für |
|-----------|----------|---------------|
| Zonen auflisten | `GET /domains/` | Abgleich Config ↔ deSEC |
| Zone anlegen | `POST /domains/` | `--create-missing` |
| Zone exportieren | `GET /domains/{name}/zonefile/` | Backup (`-b`) |
| RRSets lesen | `GET /domains/{name}/rrsets/` | Soll-Ist-Abgleich |
| RRSets schreiben | `PATCH /domains/{name}/rrsets/` | Upload (`-u`), ein Aufruf je Zone |

Über 500 RRSets hinweg paginiert deSEC über einen Cursor; `dnsjinja` folgt dem
`Link`-Header selbstständig.

## Restore aus dem Backup

!!! danger "Kein Zonefile-Import in eine bestehende Zone"
    deSEC nimmt ein Zonefile nur beim **Anlegen** einer Domain entgegen. Ein
    vollständiger Restore hieße: Domain löschen, neu anlegen, Zonefile mitgeben. Dabei
    entstehen neue DNSSEC-Schlüssel, die beim Registrar hinterlegt werden müssen – mit
    Ausfallzeit. Ein Restore ist bei deSEC kein Routinevorgang.

    Der übliche Weg zurück ist stattdessen: das Template korrigieren und erneut
    hochladen. `-b` legt trotzdem vor jeder Änderung eine Sicherung ab.
