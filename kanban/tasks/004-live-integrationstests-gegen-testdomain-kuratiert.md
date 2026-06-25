---
id: 4
title: Live-Integrationstests gegen Testdomain (kuratiert, mit Reset)
status: done
priority: high
created: 2026-06-25T18:17:01.77547938+02:00
updated: 2026-06-25T18:38:40.13875971+02:00
started: 2026-06-25T18:38:40.138758415+02:00
completed: 2026-06-25T18:38:40.138758415+02:00
tags:
    - tests
    - integration
depends_on:
    - 1
    - 2
class: standard
---

Kuratierte echte Upload-/Verify-Tests gegen 0x2e6b6169-test.de via Hetzner Cloud API. Pro Fall: Template rendern -> upload_zone() -> get_rrset_all() verifizieren. Repraesentative Faelle: minimal, mail+www, subdomains, custom_groups, full-feature. Lebenszyklus (anlegen/aendern/loeschen von RRSets) ist bereits in test_integration.py vorhanden -> auf testdata-Templates umstellen. Teardown-Fixture: Zone am Ende auf minimal (nur NS) zuruecksetzen. Tests mit pytest.mark.integration, ueberspringen ohne Token/Domain. Serialisiert (eine Zone) - ggf. xdist-group/Reihenfolge beachten.

[[2026-06-25]] Thu 18:38
TestTestdataLiveSync ergaenzt; Assertion an reales Template-Verhalten (intrinsischer custom/<domain>.inc) angepasst. 11 Integrationstests live gruen.
