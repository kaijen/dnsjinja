# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Provider abstraction & plugin system (#9):** the DNS provider API is now
  hidden behind a provider-neutral `DnsProvider` interface
  (`dnsjinja.providers`). Providers are loaded as plugins via the
  `dnsjinja.providers` entry-point group (or an explicit `module:Class`
  import path). Hetzner is shipped as the first plugin
  (`dnsjinja.providers.hetzner`); the core no longer imports `hcloud`.
- **Multiprovider support (#10):** a single `config.json` can route domains to
  different named providers. New `global.providers` map (name → definition),
  optional `global.default-provider`, and an optional per-domain `provider`
  field. Each provider is queried for its zones exactly once; a failing
  provider isolates only its own domains. Credentials per provider via
  `token-env` (falls back to `--auth-api-token` for the single-provider case).

### Changed
- Config schema validates provider references (`default-provider` and per-domain
  `provider` must exist in `global.providers`).
- Offline unit tests run against an in-memory `FakeProvider` instead of mocking
  `hcloud`; the only remaining hcloud mock is in the Hetzner-plugin test.

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
