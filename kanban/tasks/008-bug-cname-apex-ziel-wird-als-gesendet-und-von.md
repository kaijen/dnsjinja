---
id: 8
title: 'Bug: CNAME-Apex-Ziel wird als "@" gesendet und von Hetzner abgelehnt'
status: done
priority: high
created: 2026-06-25T20:41:35.875797357+02:00
updated: 2026-06-25T20:53:44.766131282+02:00
started: 2026-06-25T20:47:27.010103334+02:00
completed: 2026-06-25T20:47:27.010103334+02:00
tags:
    - bug
    - upload
    - hetzner
class: standard
---

## Problem

`_parse_zone_rrsets()` in `src/dnsjinja/dnsjinja.py` serialisiert RDATA-Werte
mit `relativize=True`. Ein CNAME, dessen Ziel der Zonen-Apex ist
(z. B. `kai IN CNAME haleb.de.` oder `* IN CNAME {{domain}}.`), wird dadurch
zu `@` kollabiert.

Hetzners RRSet-API akzeptiert `@` als **Owner-Namen**, aber **nicht** als
CNAME-**Wert** und antwortet mit:

    contains invalid characters (invalid_input)

Folge: `upload_zone()` wirft `UploadError`, der Upload der Domain bricht ab,
und der Publish-Workflow endet via `exit_on_error` mit Exit 254.

## Betroffen (Praxis: Repo dns_hetzner)

- `haleb.de` — `kai`, `www` → CNAME aufs Apex
- `enl-ka.de`, `enlightened-karlsruhe.de`, `enlka.de` — Wildcard `* CNAME @`

Hetzner speichert diese Records live korrekt als FQDN, z. B.
`kai CNAME haleb.de.` — genau das Format, das `relativize=True` zerstört.

## Fix

In `_parse_zone_rrsets()` die RDATA-Serialisierung auf `relativize=False`
umstellen:

    records = sorted(
        r.to_text(origin=origin, relativize=False) for r in rdataset
    )

Wirkung:
- Apex-Ziel `haleb.de.` statt `@`; relatives `verify` -> `verify.enl-ka.de.`
- Owner-Namen bleiben unveraendert relativ inkl. `@` (separate Logik in
  `rel_name`, nicht betroffen).
- Externe Ziele (`mailbox.org.` etc.) bleiben identisch -> keine Regression
  fuer die bereits funktionierenden Domains.

## Tests

- `tests/test_unit.py`: `_parse_zone_rrsets` fuer eine Zone mit Apex-CNAME
  pruefen -> erwartet FQDN-Wert (`<zone>.`), NICHT `@`.
- Within-zone relatives Ziel (`join CNAME verify`) -> erwartet
  `verify.<zone>.` statt `verify`.
- Regressionsschutz: Owner-Namen weiterhin relativ inkl. `@` fuer
  Apex-Records.
- Optional `tests/test_integration.py` (Marker `integration`) gegen
  Testdomain: Apex-CNAME anlegen und erfolgreichen Upload verifizieren.

## Hinweis Release

Der Publish-Workflow in dns_hetzner installiert `dnsjinja@${DNSJINJA_VER}`.
Nach dem Fix neues Tag (z. B. v1.0.1) noetig und `DNSJINJA_VER` dort
hochsetzen.

[[2026-06-25]] Thu 20:47
Fix angewendet: _parse_zone_rrsets nutzt relativize=False. Tests TestParseZoneRRSets + angepasste Config-Cases grün (66 passed).

[[2026-06-25]] Thu 20:53
Fix in dnsjinja v1.0.1 (relativize=False in _parse_zone_rrsets) released und produktiv verifiziert: Publish-Workflow grün, 42/42 Zonen gesynct, Apex-CNAMEs der zuvor fehlgeschlagenen Domains (haleb.de, enl-ka.de, enlightened-karlsruhe.de, enlka.de) jetzt korrekt als FQDN.
