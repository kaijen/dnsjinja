---
id: 5
title: Gesamte Test-Suite ausfuehren und gruen machen (Verifikation)
status: done
priority: high
created: 2026-06-25T18:17:10.988941237+02:00
updated: 2026-06-25T18:44:20.702744479+02:00
started: 2026-06-25T18:44:20.702743178+02:00
completed: 2026-06-25T18:44:20.702743178+02:00
tags:
    - tests
    - verify
depends_on:
    - 3
    - 4
class: standard
---

Erfolgskriterium der Gesamtaufgabe: pytest (offline) vollstaendig gruen ohne Netz; pytest -m integration gruen mit gesetztem Token+Domain. Coverage der Konfigurationsdimensionen gegen-checken. pyproject.toml: pytest-Marker 'integration' registriert, Testpfade korrekt. Bestehende test_unit.py/test_integration.py auf testdata umgestellt und weiterhin gruen.

[[2026-06-25]] Thu 18:38
Gesamtsuite: 63 passed (52 offline + 11 live).

[[2026-06-25]] Thu 18:44
Finale Gesamtsuite: 73 passed (62 offline + 11 live). TTL-Konvention 300s offline+live geprueft.
