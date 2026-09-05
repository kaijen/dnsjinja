# AGENT.md - DNSJinja

## Project Overview

DNSJinja is a Python CLI tool for managing DNS zones at Hetzner. It uses Jinja2 templates to generate BIND9-compatible zone files and deploys them via the Hetzner Cloud API.

- **Language:** Python 3.10+
- **License:** MIT
- **Version:** 0.3.0
- **Package name:** `dnsjinja-kaijen`
- **Author:** Kai Jendrian
- **Repository:** https://github.com/kaijen/dnsjinja

## Architecture & Directory Structure

```
DNSJinja/                                    # Tool repository
├── src/dnsjinja/                            # Main package source
│   ├── __init__.py                          # Package exports (DNSJinja, main, explore_main, exit_on_error)
│   ├── __main__.py                          # Entry point for `python -m dnsjinja`
│   ├── dnsjinja.py                          # Core class and CLI - backend-neutral
│   ├── backends/                            # DNS backend layer (the provider-specific part)
│   │   ├── base.py                          # Neutral types + DNSBackend ABC
│   │   ├── registry.py                      # Name -> class, builtins + entry points
│   │   ├── hetzner.py                       # Hetzner Cloud backend (hcloud)
│   │   └── desec.py                         # deSEC backend (requests)
│   ├── dnsjinja_config_schema.py            # pydantic v2 models for config validation
│   ├── explore_dns.py                       # Zone discovery utility (any backend)
│   ├── exit_on_error.py                     # Cross-process exit code handler
│   └── myloadenv.py                         # Multi-path .env file loader
├── samples/                                 # Sample configuration and templates
│   ├── dnsjinja.env.sample                  # Environment variable template
│   ├── dnsjinja.ps1.sample                  # PowerShell wrapper script
│   ├── config.json.sample                   # Full sample configuration
│   └── templates/                           # Sample template set (see Template Architecture)
├── tests/                                   # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py                          # Fixtures, .env loading, mock helpers
│   ├── fake_backend.py                      # In-memory backend used by the offline tests
│   ├── test_unit.py                         # Unit tests (fully mocked, no network)
│   ├── test_config_cases.py                 # Rendering per config variant (offline)
│   ├── test_backends.py                     # Registry and plugin contract
│   ├── test_backend_hetzner.py              # Hetzner backend against a mocked hcloud client
│   ├── test_backend_desec.py                # deSEC backend at HTTP level (requests-mock)
│   ├── test_normalize.py                    # TTL/RDATA normalisation, display-vs-upload parity
│   └── test_integration.py                  # Integration tests (real API)
├── pyproject.toml                           # Package metadata, dependencies, entry points, pytest
├── requirements.txt                         # Pip dependencies
├── README.md                                # Documentation (German)
└── TODO.md                                  # Planned improvements
```

## Data Repository Structure

DNSJinja separates the tool from the data. Configuration and templates are stored in a separate data repository:

```
<data-repo>/
├── config/
│   └── config.json                          # Domain configuration
├── templates/
│   ├── standard.tpl                         # Main template (entry point)
│   └── include/
│       ├── 00-ttl.inc                       # $ORIGIN and $TTL directives
│       ├── 00-meta.inc                      # SOA + NS + subdomain meta (dynamic provider selection)
│       ├── 00-subdomain-meta.inc            # Mail/WWW/XMPP provider includes + custom records
│       ├── soa/
│       │   └── soa_<provider>.inc           # SOA records (one per DNS provider)
│       ├── ns/
│       │   └── ns_<provider>.inc            # NS records (one per DNS provider)
│       ├── mail/
│       │   └── mail_<provider>.inc          # Mail records: MX, SPF, DKIM, DMARC, SRV
│       ├── www/
│       │   └── www_<provider>.inc           # Web records: A/AAAA for apex + www
│       ├── xmpp/
│       │   └── xmpp_<provider>.inc          # XMPP SRV records
│       ├── custom/
│       │   └── <domain>.inc                 # Per-domain custom DNS records
│       ├── custom-groups/
│       │   └── <group-name>.inc             # Shared configs for multiple domains
│       └── validation/
│           └── <domain>.inc                 # Domain ownership TXT records
├── zone-files/                              # Generated zone output (gitignored)
└── zone-backups/                            # Hetzner zone backups (gitignored)
```

A complete sample data set is provided in `samples/`.

## Core Modules

### `dnsjinja.py` - Main Module

Contains the `DNSJinja` class with all core logic:

- **`DEFAULT_BACKEND`** - Class constant: `hetzner`
- **`__init__(upload, backup, write_zone, datadir, config_file, auth_api_token)`** - Loads config, validates schema, resolves the backend, sets up Jinja2 environment, prepares zones
- **`_resolve_backend(token)`** - Reads `global.dns-backend`, resolves the class through the registry, applies the token precedence (CLI option, `DNSJINJA_<BACKEND>_AUTH_API_TOKEN`, `DNSJINJA_AUTH_API_TOKEN`) and instantiates the backend
- **`_prepare_zones()`** - Syncs configured domains via `backend.list_zones()`, auto-populates `zone-id`, `zone-file` and stores neutral `Zone` objects in `_zones`. With `_create_missing`, creates missing zones via `backend.create_zone()`
- **`_parse_zone_rrsets(domain)`** - Parses the rendered zone into the canonical dnsjinja form (relative owner names, `@` for the apex, absolute RDATA). **Must stay backend-free** - `test_config_cases.py` asserts on exactly this form
- **`_plan_zone_rrsets(domain)`** - Normalises the desired state through `backend.normalize_desired()`, reads the live state through `backend.list_rrsets()` and returns the diff. The single common root of display and upload, which is why normalisation belongs here
- **`_sync_zone_rrsets(domain)`** - Filters the plan and hands it to `backend.apply_changes()`
- **`_get_zone_serial(domain)`** - Queries SOA serial from the configured nameservers via dnspython
- **`_new_zone_serial(domain)`** - Generates SOA serial in `YYYYMMDD##` format (auto-incrementing counter)
- **`_create_zone_data()`** - Renders all Jinja2 templates into zone file content
- **`write_zone_files()`** - Writes rendered zones to local files as `{domain}.zone.{serial}`
- **`upload_zone(domain)`** - Applies the change plan; reports skipped RRSets instead of claiming plain success
- **`upload_zones()`** - Uploads all configured zones, continues on individual failures
- **`backup_zone(domain)`** - Exports zone data via `backend.export_zonefile(zone)`
- **`backup_zones()`** - Backs up all configured zones

Custom exception: `UploadError` - raised on upload failure, writes exit code 254 to temp file.

CLI function `run()` uses Click with options for `--datadir`, `--config`, `--upload`, `--backup`, `--write`, `--create-missing`, `--auth-api-token`.

### `backends/` - DNS Backend Layer

Everything provider-specific lives here; the core knows only the neutral types.

- **`base.py`** - `RRSet`, `Zone`, `RRSetChange`, `ApplyResult`, `BackendCapabilities`, the `BackendError` hierarchy, and the `DNSBackend` ABC. Also the concrete normalisation (`normalize_desired`, `canonicalize_rdata`, `effective_min_ttl`) that every backend inherits.
- **`registry.py`** - Resolves a name to a class: builtins first (lazily imported), then the `dnsjinja.backends` entry point group. A broken plugin is logged and skipped. `config.json` never names a module path.
- **`hetzner.py`** - hcloud-based. Per-RRSet action endpoints, so `apply_changes()` is a loop and not atomic; a failed delete lands in `ApplyResult.skipped`.
- **`desec.py`** - requests-based. `apply_changes()` builds one atomic bulk PATCH. Owns the apex wire-form conversion (`@` <-> `""`), cursor pagination and 429 handling.

The contract: `apply_changes()` is the only writing entry point and receives the **complete** plan. That is what lets both API shapes live behind one interface.

### `dnsjinja_config_schema.py` - Config Schema

pydantic v2 models (`DnsJinjaConfig`, `GlobalConfig`, `DomainConfig`), all with `extra='allow'`:
- **`global`** (required): `zone-files`, `zone-backups`, `templates`, `name-servers`. Optional: `dns-backend` (default `hetzner`), `dns-api-base` (default: the backend's own), `backend-options`.
- **`domains`**: Object keyed by domain name, each with `template` (required). Additional properties allowed for template variables.

Note: `model_validate()` result is discarded in `DNSJinja.__init__`; the code reads the raw dict, so **schema defaults must be repeated at the read site**.

`zone-id` and `zone-file` are auto-populated by `_prepare_zones()` at runtime.

### `explore_dns.py` - Zone Discovery

`ExploreDNS` fetches all zones through `backend.list_zones()` and outputs a JSON config template. `-B/--dns-backend` picks the backend, `--list-backends` shows what is available. The old command name `explore_hetzner` remains as an alias.

### `myloadenv.py` - Environment Loader

`load_env()` searches multiple platform-aware paths for `.env` and `{module}.env` files using `platformdirs` and `python-dotenv`. Paths include `~/`, `~/.config/`, `~/.dnsjinja/`, user config dir, and CWD.

### `exit_on_error.py` - Exit Code Handler

Reads exit code from `{tempdir}/dnsjinja.exit.txt` and calls `sys.exit()` with that code. Used to propagate error codes across process boundaries (especially on Windows).

## Dependencies

| Package | Purpose |
|---------|---------|
| Jinja2 | Template rendering for zone files |
| hcloud | Official Hetzner Cloud Python client (zones API) |
| requests | HTTP client for the deSEC backend |
| dnspython | DNS resolver for SOA serial queries |
| Click | CLI framework with env var support |
| python-dotenv | .env file loading |
| pydantic | Config validation |
| platformdirs | Cross-platform config directory detection |

## CLI Commands & Environment Variables

### Entry Points (defined in `pyproject.toml`)

| Command | Entry Point | Purpose |
|---------|-------------|---------|
| `dnsjinja` | `dnsjinja:main` | Main CLI - backup, write, upload zones |
| `explore_dns` | `dnsjinja:explore_main` | Discover zones, generate config template |
| `explore_hetzner` | `dnsjinja:explore_main` | Alias for `explore_dns` |
| `exit_on_error` | `dnsjinja:exit_on_error` | Check and propagate exit codes |

Backends are entry points too, in group `dnsjinja.backends`:

| Name | Entry Point |
|------|-------------|
| `hetzner` | `dnsjinja.backends.hetzner:HetznerBackend` |
| `desec` | `dnsjinja.backends.desec:DesecBackend` |

### `dnsjinja` Options

| Option | Default | Env Var | Description |
|--------|---------|---------|-------------|
| `-d`, `--datadir` | `.` | `DNSJINJA_DATADIR` | Base directory for templates and config |
| `-c`, `--config` | `config/config.json` | `DNSJINJA_CONFIG` | Configuration file path |
| `-u`, `--upload` | `False` | - | Upload zones to the backend |
| `-b`, `--backup` | `False` | - | Backup zones from the backend |
| `-w`, `--write` | `False` | - | Write zone files locally |
| `-C`, `--create-missing` | `False` | - | Create zones that are configured but not yet present |
| `--auth-api-token` | `""` | `DNSJINJA_AUTH_API_TOKEN` | API token; `DNSJINJA_<BACKEND>_AUTH_API_TOKEN` takes precedence over the general variable |
| `--dry-run` | `False` | - | Render and print zone files, write and upload nothing |
| `--dry-run-compare` | `False` | - | Show live-vs-template differences, change nothing |
| `--show-ttl` | `False` | - | With `--dry-run-compare`, also list TTL-only differences |

### `explore_dns` Options

| Option | Default | Env Var | Description |
|--------|---------|---------|-------------|
| `-o`, `--output` | stdout | - | Output file for results |
| `-B`, `--dns-backend` | `hetzner` | `DNSJINJA_DNS_BACKEND` | Backend to query |
| `--auth-api-token` | `""` | `DNSJINJA_AUTH_API_TOKEN` | API token for the backend |
| `--api-base` | `""` | `DNSJINJA_API_BASE` | Base URL of the API |
| `--list-backends` | `False` | - | List available backends and exit |

## Configuration Format

The `config.json` has two sections: `global` (infrastructure settings) and `domains` (per-domain configuration).

### Domain Entry Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `template` | yes | string | Jinja2 template filename (e.g. `standard.tpl`) |
| `mail` | no | string | Mail provider name (selects `include/mail/mail_<value>.inc`) |
| `www` | no | string | Web provider name (selects `include/www/www_<value>.inc`) |
| `xmpp` | no | string | XMPP provider name (selects `include/xmpp/xmpp_<value>.inc`) |
| `registrar` | no | string | Registrar name (stored as TXT record) |
| `subdomains` | no | array | List of subdomains to process as additional zones |
| `custom_groups` | no | array | List of shared configuration groups to include |
| `zone-id` | auto | string | Hetzner zone ID (auto-populated from API) |
| `zone-file` | auto | string | Output filename (auto-populated) |

All domain config fields are passed to templates as Jinja2 variables via `**kwargs`.

### Global Section Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `zone-files` | yes | - | Directory for generated zone files |
| `zone-backups` | yes | - | Directory for zone backups |
| `templates` | yes | - | Directory for Jinja2 templates |
| `name-servers` | yes | - | IPv4 addresses for SOA serial queries |
| `dns-backend` | no | `hetzner` | DNS backend name (`hetzner`, `desec`, or a plugin) |
| `dns-api-base` | no | the backend's own | Base URL of the API |
| `backend-options` | no | `{}` | Backend-specific settings (e.g. `timeout`, `rate-limit-retries`) |

### Example

```json
{
  "global": {
    "zone-files": "zone-files",
    "zone-backups": "zone-backups",
    "templates": "templates",
    "name-servers": ["213.133.100.98", "88.198.229.192", "193.47.99.5"]
  },
  "domains": {
    "example.com": {
      "template": "standard.tpl",
      "mail": "example-provider",
      "www": "example-provider",
      "xmpp": "example-provider",
      "registrar": "Hetzner",
      "subdomains": ["blog", "dev"],
      "custom_groups": ["shared-hosting"]
    }
  }
}
```

See `samples/config.json.sample` for a complete example with multiple domain configurations.

## Hetzner Cloud API

DNSJinja uses the official [hcloud-python](https://github.com/hetznercloud/hcloud-python) library to communicate with the Hetzner Cloud API (`https://api.hetzner.cloud/v1`). HTTP handling, authentication, and pagination are managed by the library.

### External References

- [Hetzner Cloud API – Zone Actions](https://docs.hetzner.cloud/reference/cloud#tag/zone-actions)
- [hcloud-python – Official Hetzner Cloud Python Client](https://github.com/hetznercloud/hcloud-python)

### hcloud Client Methods Used

| Operation | Hetzner (hcloud) | deSEC |
|-----------|------------------|-------|
| List zones | `client.zones.get_all()` | `GET /domains/` |
| Create zone | `client.zones.create(name, mode="primary")` | `POST /domains/` |
| Export zone | `client.zones.export_zonefile(zone)` | `GET /domains/{name}/zonefile/` |
| Import zone | `client.zones.import_zonefile(zone, zonefile)` | only when creating a domain |
| List RRSets | `client.zones.get_rrset_all(zone)` | `GET /domains/{name}/rrsets/` (cursor) |
| Apply changes | `create_rrset` / `set_rrset_records` + `change_rrset_ttl` / `delete_rrset`, one call each | one atomic `PATCH /domains/{name}/rrsets/` |

Both are reached only through `DNSBackend`; `dnsjinja.py` calls neither library directly.
Hetzner tokens come from the Cloud Console (not the old dns.hetzner.com portal), deSEC
tokens from Token Management. deSEC uses `Authorization: Token <secret>`, not Bearer.

## Workflow

The main CLI executes three phases in order (each gated by its flag):

1. **Backup** (`-b`): Exports current zones through the backend, saves as `{zone-file}.{serial}` in `zone-backups/`
2. **Write** (`-w`): Renders Jinja2 templates for each domain, writes as `{zone-file}.{serial}` in `zone-files/`
3. **Upload** (`-u`): Plans the diff and hands it to `backend.apply_changes()` for each domain

On initialization, `_prepare_zones()` always runs to sync configured domains against Hetzner's zone list (with pagination) and warn about mismatches.

## Template Architecture

Templates use a modular include-based architecture with dynamic provider selection.

### Rendering Flow

```
standard.tpl (entry point per domain)
├── include/00-ttl.inc              → $ORIGIN + $TTL
├── include/00-meta.inc             → SOA + NS + base domain records
│   ├── include/soa/soa_<soa|default('hetzner')>.inc
│   ├── include/ns/ns_<ns|default('hetzner')>.inc
│   └── include/00-subdomain-meta.inc
│       ├── include/mail/mail_<mail|default('none')>.inc    (ignore missing)
│       │   └── include/validation/<domain>.inc             (ignore missing)
│       ├── include/xmpp/xmpp_<xmpp|default('none')>.inc   (ignore missing)
│       ├── include/www/www_<www|default('none')>.inc       (ignore missing)
│       ├── include/custom/<domain>.inc                     (ignore missing)
│       └── for each custom_group:
│           └── include/custom-groups/<group>.inc            (ignore missing)
└── for each subdomain:
    ├── include/00-ttl.inc          → $ORIGIN for <sub>.<domain>
    └── include/00-subdomain-meta.inc → same provider includes for subdomain
```

### Key Jinja2 Mechanisms

- **Dynamic includes:** Provider filenames are constructed from config values via string concatenation: `'include/mail/mail_' + mail|default('none') + '.inc'`
- **`ignore missing`:** Optional includes are silently skipped if the file doesn't exist (e.g. no custom records for a domain)
- **`|default()` filter:** Provides fallback values when config fields are omitted (e.g. `soa|default('hetzner')`)
- **Variable shadowing:** `domain` is reassigned to `<subdomain>.<domain>` inside the subdomain loop, enabling the same includes to work for both base domains and subdomains
- **Whitespace control:** `+%}` strips trailing whitespace after Jinja2 tags to produce clean zone files
- **`hostname` filter:** Custom filter resolving hostnames to IPv4 via `socket.gethostbyname()` (available in templates as `{{ "host.example.com" | hostname }}`)

### Template Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `domain` | auto + loop | Current domain being processed (reassigned for subdomains) |
| `soa_serial` | auto | SOA serial in `YYYYMMDD##` format |
| `mail` | config | Mail provider selector |
| `www` | config | Web provider selector |
| `xmpp` | config | XMPP provider selector |
| `soa` | config | SOA provider selector (defaults to `hetzner`) |
| `ns` | config | NS provider selector (defaults to `hetzner`) |
| `registrar` | config | Registrar name for TXT record |
| `subdomains` | config | List of subdomains to process |
| `custom_groups` | config | List of shared config groups |

### Adding a New Provider

Note: "provider" here means a **service provider at template level** (mail, www, xmpp, ns,
soa). Which API the zones are uploaded through is a separate concept - the **backend**,
selected by `global.dns-backend`. Do not conflate the two.

1. Create `include/<category>/<category>_<name>.inc` (e.g. `include/mail/mail_newprovider.inc`)
2. Reference it in domain config: `"mail": "newprovider"`

### Adding a New Backend

1. Subclass `dnsjinja.backends.DNSBackend`, implement `list_zones()`, `create_zone()`,
   `export_zonefile()`, `list_rrsets()`, `apply_changes()`, and declare `BackendCapabilities`
2. Map every provider exception onto the `BackendError` hierarchy - no foreign exception
   may leave a backend
3. Register it under the `dnsjinja.backends` entry point group (in-tree: also add it to
   `_BUILTIN` in `registry.py`)

### Adding Custom Records for a Domain

1. Create `include/custom/<domain>.inc` with the DNS records
2. No config change needed - auto-included if the file exists

### Adding Shared Configuration Groups

1. Create `include/custom-groups/<name>.inc`
2. Reference in domain config: `"custom_groups": ["<name>"]`

## CI/CD Integration

DNSJinja can be integrated into GitHub Actions to auto-deploy DNS changes on push:

1. Data repository triggers workflow on push to `main`
2. Workflow installs `dnsjinja` from its repository
3. Checks out the data repository
4. Runs `dnsjinja -b -w -u` (backup, write, upload)
5. Stores zone-files and zone-backups as build artifacts
6. Checks exit status via `exit_on_error`

Required GitHub secrets/variables:
- `HETZNER_API_AUTH_TOKEN` (secret) - Hetzner API token
- `GH_PAT_DNSJINJA` (secret) - GitHub PAT for installing dnsjinja from private repo
- `DNSJINJA` (var) - Repository path for dnsjinja tool
- `DNSDATA` (var) - Repository path for DNS data

## Docker

Multi-stage `Dockerfile` with two targets, managed via `docker-compose.yml`.

### Targets

| Target | Install | Use Case |
|--------|---------|----------|
| `prod` | `pip install .` | Production: run dnsjinja against a volume-mounted data repo |
| `dev` | `pip install -e .` | Development: editable install with live source mount |

Base image: `python:3.12-slim`. Working directory: `/data` (mount point for data repo).

### docker-compose Services

| Service | Target | Extra Volumes |
|---------|--------|---------------|
| `dnsjinja` | prod | `${DNSJINJA_DATADIR}:/data` |
| `dnsjinja-dev` | dev | `${DNSJINJA_DATADIR}:/data`, `./src:/app/src` |

Usage: `docker compose run --rm dnsjinja -b -w -u`

### Environment Variables in Container

| Variable | Value in Container | Source |
|----------|-------------------|--------|
| `DNSJINJA_AUTH_API_TOKEN` | passed from host | `docker -e` or compose `environment:` |
| `DNSJINJA_DATADIR` | `/data` | set in compose |
| `DNSJINJA_CONFIG` | `/data/config/config.json` | set in compose |

The `ENTRYPOINT` is `dnsjinja`. To run `explore_dns`, use `--entrypoint explore_dns`.

## Coding Conventions

- **Naming:** `snake_case` for functions/methods, `CamelCase` for classes
- **UI/comments language:** German (user-facing messages, comments, docstrings)
- **File paths:** `pathlib.Path` throughout for cross-platform compatibility
- **CLI:** Click framework with environment variable fallbacks
- **Error handling:** `sys.exit(1)` for fatal errors, custom `UploadError` for upload failures, batch operations continue on individual failures
- **Traceback suppression:** `sys.tracebacklimit = 0` in `__main__.py` for clean user output
- **No type hints** used in the codebase
- **No logging framework** - uses `print()` for all output
- **Tests:** pytest with `unittest.mock` (no extra mock library); unit tests fully isolated, integration tests require env vars

## Testing

### Unit Tests (no network required)

```bash
pip install -e ".[test]"
pytest tests/test_unit.py -v
```

All Hetzner API calls and DNS queries are mocked via `unittest.mock`. The fixture `data_dir` creates a temporary directory with a minimal `test.tpl` template. `mock_client` patches `dnsjinja.dnsjinja.Client`; `mock_dns_resolver` patches `dns.resolver.Resolver`.

Covered areas:

| Class | What is tested |
|-------|---------------|
| `TestPrepareZones` | Zone sync, `--create-missing`, API errors, extra Hetzner zones |
| `TestUploadZone` | Success path, failure → exit code 254, continues on partial failure |
| `TestBackupZone` | File written, filename contains serial, API error handling |
| `TestWriteZoneFiles` | File creation, disabled mode |
| `TestZoneSerial` | Increment on same day, reset to 01 on new day, format |

### Integration Tests (requires Hetzner API)

```bash
export DNSJINJA_AUTH_API_TOKEN=<token>   # Bearer token from Hetzner Cloud Console
export DNSJINJA_TEST_DOMAIN=<domain>     # Must already exist as primary zone at Hetzner
pytest tests/test_integration.py -m integration -v
```

Or via `.env` / `$HOME/.dnsjinja/dnsjinja.env`. Integration tests are skipped automatically when env vars are not set.

> **Note:** `TestUpload::test_upload_erfolgreich` replaces all DNS records of the test domain with a minimal zone file. Use a dedicated test domain.

### conftest.py – Key Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `api_token` | session | `DNSJINJA_AUTH_API_TOKEN` env var |
| `test_domain` | session | `DNSJINJA_TEST_DOMAIN` env var |
| `require_api_token` | session | Skip test if token not set |
| `require_test_domain` | session | Skip test if domain not set |
| `data_dir` | function | `tmp_path` with config/, templates/, zone-files/, zone-backups/ |
| `config_file` | function | `config.json` with `example.com` |
| `mock_client` | function | Patches `dnsjinja.dnsjinja.Client` |
| `mock_dns_resolver` | function | Patches `dns.resolver.Resolver`, returns serial `2026020101` |

## Known Limitations & TODOs

- Templates stored in separate external repository
- German-only user interface
