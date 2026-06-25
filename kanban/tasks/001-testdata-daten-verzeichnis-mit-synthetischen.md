---
id: 1
title: testdata/ Daten-Verzeichnis mit synthetischen Templates anlegen (Vorbild tmp/dns_hetzner/)
status: done
priority: high
created: 2026-06-25T18:16:39.321702836+02:00
updated: 2026-06-25T18:24:09.455627233+02:00
started: 2026-06-25T18:24:09.455625824+02:00
completed: 2026-06-25T18:24:09.455625824+02:00
tags:
    - testdata
    - templates
class: standard
---

Neues, eingechecktes Verzeichnis testdata/ als Test-Fixture, strukturell nach tmp/dns_hetzner/ modelliert, aber mit synthetischen Platzhaltern (RFC-5737-IPs 192.0.2.x/198.51.100.x, Beispiel-DKIM/Validation-Tokens, generische Provider). Inhalt: testdata/config/config.json (Domains -> Feature-Kombinationen), testdata/templates/standard.tpl + include/ (00-ttl.inc, 00-meta.inc, 00-subdomain-meta.inc, soa/soa_hetzner.inc, ns/ns_hetzner.inc, mail/*, www/*, xmpp/*, custom/*, custom-groups/*, validation/*), leere testdata/zone-files/ und testdata/zone-backups/ (.gitkeep). Zieldomain der Live-Tests: 0x2e6b6169-test.de. Abdeckung aller Konvention-Includes: mail_<x>, www_<x>, xmpp_<x>, custom/<domain>, custom-groups/<cg>, validation/<domain>, subdomains, registrar, ns/soa-Override.

[[2026-06-25]] Thu 18:24
testdata/ erstellt (synthetische Templates + config). Alle 10 Domains rendern zu gueltigem BIND-Zonefile und parsen zu RRSets. .gitignore-Ausnahme fuer testdata/config/config.json ergaenzt.
