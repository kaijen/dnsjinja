# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- DNS backends are now pluggable and selected via `global.dns-backend` in
  `config.json`. Two backends ship with dnsjinja: `hetzner` (the default, and
  the previous behaviour) and `desec`. `explore_dns --list-backends` lists what
  is available.
- A deSEC backend. It sends the complete change plan as one atomic bulk `PATCH`,
  deletes via an empty records array, follows Link-header cursor pagination and
  honours `Retry-After` on 429. Because deSEC signs zones itself, SOA and all
  DNSSEC-adjacent types are excluded from the comparison on both sides;
  otherwise every signed record would be planned for deletion.
- Third-party packages can contribute backends through the `dnsjinja.backends`
  entry point group. `config.json` names backends only, never a module path — a
  config file must not decide which code runs. A plugin that fails to load is
  logged and skipped rather than taking the run down with it.
- A normalisation layer that adapts rendered zone data to the limits of the
  selected backend: TTLs below the minimum are raised (deSEC requires 3600 while
  the templates use `$TTL 300`), TTLs above the maximum are capped, provider-
  managed record types are dropped and RDATA is canonicalised — including
  splitting TXT values longer than 255 bytes, which providers do server-side.
  This runs inside `_plan_zone_rrsets()`, so `--dry-run-compare` and the actual
  upload cannot see different data.
- `backend-options` in `config.json` carries backend-specific settings
  (`timeout`, `rate-limit-retries`) without the core schema having to know them.
- `DNSJINJA_<BACKEND>_AUTH_API_TOKEN` (e.g. `DNSJINJA_DESEC_AUTH_API_TOKEN`)
  takes precedence over `DNSJINJA_AUTH_API_TOKEN`, so both providers can be
  configured side by side.
- `soa_desec.inc` and `ns_desec.inc` template includes.
- `--dry-run-compare` shows the differences between the live RRSets at Hetzner
  and the rendered templates (new / changed / deleted / protected records) per
  domain, without changing anything.
- `--show-ttl` additionally lists RRSets that differ only in their TTL. These
  are hidden by default, since templates set the TTL globally via `$TTL` rather
  than per record. Note that the upload still aligns the TTL either way; the
  summary points this out whenever TTL-only differences were hidden.

### Changed
- `explore_hetzner` is now `explore_dns` and takes `-B/--dns-backend`. The old
  command name remains as an alias.
- `dns-api-base` no longer defaults to the Hetzner URL; when unset, the selected
  backend's own default applies. Configurations that set it explicitly are
  unaffected.
- The upload reports the number of skipped RRSets instead of always claiming
  success. Hetzner applies changes one at a time, so a partially applied zone is
  possible there; deSEC applies all or nothing.
- Provider-specific code moved out of `DNSJinja` into `dnsjinja.backends`. The
  core works with neutral types (`RRSet`, `Zone`, `RRSetChange`, `ApplyResult`)
  and a single writing entry point, `DNSBackend.apply_changes()`, which receives
  the complete plan. That is what lets per-record action endpoints and an atomic
  bulk request live behind the same interface.
- The `registrar` TXT record is now emitted once at the zone apex instead of
  once per subdomain. A registrar registers the domain, not its subdomains, so
  the previous `registrar.<sub>` records described nothing real. Zones that use
  `subdomains` will lose those records on the next `--upload`; only the apex
  `registrar` record remains.
- The `registrar` TXT value is now quoted, so registrar names containing
  spaces no longer produce an invalid record.
- The RRSet comparison used by `--upload` was extracted into
  `_plan_zone_rrsets()`, so the upload and the new compare output are derived
  from the same logic and cannot drift apart.

### Fixed
- A SOA serial that does not follow the `YYYYMMDDNN` format no longer raises
  `ValueError`. Providers that maintain the SOA record themselves number
  differently; the serial only feeds rendered zone files and backup filenames,
  so the run now restarts today's counter at `01` and continues.
- `requirements.txt` listed `jsonschema` and `appdirs`, which the project
  dropped for `pydantic` and `platformdirs`, and was missing `pydantic`.
- A zone whose SOA cannot be resolved no longer aborts the run. A newly created
  domain has to exist at Hetzner before it can be registered and delegated, so
  its nameservers answer `REFUSED` until then. dnsjinja now warns and starts the
  serial at `YYYYMMDD01` instead of exiting. The serial is only used for rendered
  zone files and backup filenames — Hetzner manages the SOA record itself.
- The SOA serial is now queried once per domain and run instead of once per
  serial lookup, so backups no longer trigger a second DNS query.
- `--create-missing` is now ignored in both dry-run modes. Previously
  `--dry-run -C` created missing zones at Hetzner during what is supposed to be
  a read-only run.

## [1.0.1] - 2026-06-25

### Fixed
- CNAME targets pointing at the zone apex are now serialized as a FQDN
  (e.g. `example.com.`) instead of collapsing to `@`, which Hetzner rejected
  as an invalid CNAME value (`invalid_input`). Within-zone targets are
  likewise emitted as FQDNs; owner names stay relative (incl. `@`). (#8)

## [1.0.0] - 2026-06-25

### Breaking Changes
- Migrated from the legacy `dns.hetzner.com` DNS API to the Hetzner Cloud
  API (hcloud-python). Authentication now uses a Cloud API token
  (`DNSJINJA_AUTH_API_TOKEN`); the old `dns-*-api` config keys are replaced
  by the optional `dns-api-base`.
- Zones are synchronized at RRSet level instead of via full zone-file import.

### Added
- Modular Jinja2 templating for mail/www/xmpp/custom/custom_groups,
  subdomains and ns/soa overrides.
- `--create-missing` to auto-create configured zones, `--dry-run` to render
  without uploading, and pre-upload zone-syntax validation.
- Project-local `testdata/` fixture and a full offline + live test suite
  (73 tests) covering all sensible domain configurations.
- Uniform 300s TTL for all managed records.
- Docker-based deployment and development images.

### Changed
- Configuration validation via pydantic v2.
- Packaging migrated to hatchling + hatch-vcs with git-tag-derived versioning.

### Fixed
- `.env` cascade order, SOA serial overflow handling and several robustness
  issues found in code review.

[Unreleased]: https://github.com/kaijen/dnsjinja/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/kaijen/dnsjinja/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/kaijen/dnsjinja/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/kaijen/dnsjinja/releases/tag/v0.2.0
