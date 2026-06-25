---
id: 3
title: Offline-Render-Testsuite fuer alle Konfigurationsfaelle
status: done
priority: high
created: 2026-06-25T18:16:55.240077041+02:00
updated: 2026-06-25T18:29:22.175632868+02:00
started: 2026-06-25T18:29:22.175631367+02:00
completed: 2026-06-25T18:29:22.175631367+02:00
tags:
    - tests
    - offline
depends_on:
    - 1
class: standard
---

Schnelle, netzunabhaengige Tests, die fuer jede sinnvolle Domain-Konfiguration das gerenderte Zone-File pruefen (Text + via dns.zone.from_text geparste RRSets). Matrix der Faelle: (a) minimal nur NS/SOA; (b) mail=mailbox.org / antonius / spamhero / none; (c) www=bero / adobe / beromjh / none; (d) xmpp=mailbox / none; (e) subdomains=[..]; (f) custom/<domain>.inc vorhanden; (g) custom_groups=[..]; (h) validation/<domain>.inc; (i) registrar-Wert; (j) ns/soa-Override; (k) Kombinationen (z.B. mail+www+xmpp+subdomains+custom_groups); (l) fehlende optionale Includes werden ignoriert (ignore missing); (m) ungueltiger Template-Name -> exit(1); (n) Config-Schema: fehlendes template -> exit(1). Nutzt testdata/-Templates. _parse_zone_rrsets-Erwartungen pro Fall.

[[2026-06-25]] Thu 18:29
tests/test_config_cases.py + conftest build_dj-Factory. 52 Offline-Tests gruen (inkl. test_unit.py).
