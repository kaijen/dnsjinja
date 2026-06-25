---
id: 7
title: 'Dynamische Versionierung: Umstellung auf hatchling + hatch-vcs'
status: done
priority: high
created: 2026-06-25T18:46:02.81628598+02:00
updated: 2026-06-25T18:49:55.495749783+02:00
started: 2026-06-25T18:49:55.495748382+02:00
completed: 2026-06-25T18:49:55.495748382+02:00
tags:
    - packaging
    - build
class: standard
---

pyproject.toml nutzt aktuell setuptools mit statischer Version 0.3.0. Umstellung auf hatchling als Build-Backend und hatch-vcs fuer dynamische Versionierung aus Git-Tags. Per /hatch-versioning-Skill. Danach Build-/Install-Smoke-Test.

[[2026-06-25]] Thu 18:49
pyproject.toml auf hatchling+hatch-vcs umgestellt. hatch version -> 0.2.0.post31+g7e9abc36c. Build-Smoke-Test ok (Wheel korrekt, keine egg-info-Leaks, Entry-Points erhalten).
