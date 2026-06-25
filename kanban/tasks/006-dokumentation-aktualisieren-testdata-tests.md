---
id: 6
title: Dokumentation aktualisieren (testdata/, Tests ausfuehren)
status: done
priority: medium
created: 2026-06-25T18:17:15.011942023+02:00
updated: 2026-06-25T18:44:33.641409434+02:00
started: 2026-06-25T18:44:33.641407833+02:00
completed: 2026-06-25T18:44:33.641407833+02:00
tags:
    - docs
depends_on:
    - 1
    - 3
    - 4
class: standard
---

README.md / AGENT.md ergaenzen: Beschreibung des testdata/-Verzeichnisses, wie Offline- und Integrationstests ausgefuehrt werden (pytest, pytest -m integration), benoetigte Umgebungsvariablen (DNSJINJA_AUTH_API_TOKEN, DNSJINJA_TEST_DOMAIN), Warnung dass die Testdomain ueberschrieben wird. samples/ ggf. mit testdata/ abgleichen. TODO.md: Migrationsstatus festhalten.

[[2026-06-25]] Thu 18:44
README: testdata/-Fixture, TTL-300-Konvention, Offline-/Integrationstest-Abschnitte aktualisiert.
