---
id: 2
title: Testdomain 0x2e6b6169-test.de verdrahten (.env + conftest)
status: done
priority: high
created: 2026-06-25T18:16:42.693140811+02:00
updated: 2026-06-25T18:24:34.606164967+02:00
started: 2026-06-25T18:24:34.606163271+02:00
completed: 2026-06-25T18:24:34.606163271+02:00
tags:
    - testdata
    - integration
class: standard
---

DNSJINJA_TEST_DOMAIN=0x2e6b6169-test.de in .env ergaenzen, damit die Integrationstests nicht mehr uebersprungen werden. conftest.py liest die Variable bereits (require_test_domain). Pruefen, ob .env korrekt geladen wird (myloadenv/_load_env Kaskade). Doku-Hinweis: Domain ist die einzige Zone des Tokens und wird von Live-Tests ueberschrieben.

[[2026-06-25]] Thu 18:24
DNSJINJA_TEST_DOMAIN=0x2e6b6169-test.de in .env ergaenzt.
