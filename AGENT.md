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
│   ├── dnsjinja.py                          # Core class, CLI, and Hetzner Cloud API operations (~270 lines)
│   ├── dnsjinja_config_schema.py            # JSON Schema (Draft 7) for config validation (~145 lines)
│   ├── explore_hetzner.py                   # Hetzner zone discovery utility (~75 lines)
│   ├── exit_on_error.py                     # Cross-process exit code handler (~20 lines)
│   └── myloadenv.py                         # Multi-path .env file loader (~38 lines)
├── samples/                                 # Sample configuration and templates
│   ├── dnsjinja.env.sample                  # Environment variable template
│   ├── dnsjinja.ps1.sample                  # PowerShell wrapper script
│   ├── config.json.sample                   # Full sample configuration
│   └── templates/                           # Sample template set (see Template Architecture)
├── setup.cfg                                # Package metadata, dependencies, entry points
├── pyproject.toml                           # Build system configuration (setuptools)
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

- **`DEFAULT_API_BASE`** - Class constant: `https://api.hetzner.cloud/v1`
- **`__init__(upload, backup, write_zone, datadir, config_file, auth_api_token)`** - Loads config, validates schema, initializes `hcloud.Client`, sets up Jinja2 environment, prepares zones
- **`_prepare_zones()`** - Syncs configured domains with Hetzner via `client.zones.get_all()`, auto-populates `zone-id`, `zone-file` and stores `BoundZone` objects in `_hetzner_zones`. If `_create_missing` is set, creates missing zones via `client.zones.create(name, mode="primary")`
- **`_get_zone_serial(domain)`** - Queries SOA serial from Hetzner nameservers via dnspython
- **`_new_zone_serial(domain)`** - Generates SOA serial in `YYYYMMDD##` format (auto-incrementing counter)
- **`_create_zone_data()`** - Renders all Jinja2 templates into zone file content
- **`write_zone_files()`** - Writes rendered zones to local files as `{domain}.zone.{serial}`
- **`upload_zone(domain)`** - Imports zone data via `client.zones.import_zonefile(zone, zonefile)`
- **`upload_zones()`** - Uploads all configured zones, continues on individual failures
- **`backup_zone(domain)`** - Exports zone data via `client.zones.export_zonefile(zone)`
- **`backup_zones()`** - Backs up all configured zones

Custom exception: `UploadError` - raised on upload failure, writes exit code 254 to temp file.

CLI function `run()` uses Click with options for `--datadir`, `--config`, `--upload`, `--backup`, `--write`, `--create-missing`, `--auth-api-token`.

### `dnsjinja_config_schema.py` - Config Schema

Defines `DNSJINJA_JSON_SCHEMA` (JSON Schema Draft 7) with two sections:
- **`global`** (required fields): `zone-files`, `zone-backups`, `templates` (directories), `name-servers` (IPv4 array). Optional: `dns-api-base` (URI, defaults to `https://api.hetzner.cloud/v1`)
- **`domains`**: Object keyed by domain name, each with `template` (required), `zone-file` (optional). Additional properties allowed for template variables.

Note: `zone-id` and `zone-file` are auto-populated by `_prepare_zones()` from the Hetzner Cloud API at runtime.

### `explore_hetzner.py` - Zone Discovery

`ExploreHetzner` class fetches all zones via `hcloud.Client.zones.get_all()` and outputs a JSON config template. Accepts optional `api_base` parameter. Useful for initial project setup.

### `myloadenv.py` - Environment Loader

`load_env()` searches multiple platform-aware paths for `.env` and `{module}.env` files using `appdirs` and `python-dotenv`. Paths include `~/`, `~/.config/`, `~/.dnsjinja/`, user config dir, and CWD.

### `exit_on_error.py` - Exit Code Handler

Reads exit code from `{tempdir}/dnsjinja.exit.txt` and calls `sys.exit()` with that code. Used to propagate error codes across process boundaries (especially on Windows).

## Dependencies

| Package | Purpose |
|---------|---------|
| Jinja2 | Template rendering for zone files |
| hcloud | Official Hetzner Cloud Python client (zones API) |
| dnspython | DNS resolver for SOA serial queries |
| Click | CLI framework with env var support |
| python-dotenv | .env file loading |
| jsonschema | Config validation against JSON Schema |
| appdirs | Cross-platform config directory detection |

## CLI Commands & Environment Variables

### Entry Points (defined in `setup.cfg`)

| Command | Entry Point | Purpose |
|---------|-------------|---------|
| `dnsjinja` | `dnsjinja:main` | Main CLI - backup, write, upload zones |
| `explore_hetzner` | `dnsjinja:explore_main` | Discover Hetzner zones, generate config template |
| `exit_on_error` | `dnsjinja:exit_on_error` | Check and propagate exit codes |

### `dnsjinja` Options

| Option | Default | Env Var | Description |
|--------|---------|---------|-------------|
| `-d`, `--datadir` | `.` | `DNSJINJA_DATADIR` | Base directory for templates and config |
| `-c`, `--config` | `config/config.json` | `DNSJINJA_CONFIG` | Configuration file path |
| `-u`, `--upload` | `False` | - | Upload zones to Hetzner |
| `-b`, `--backup` | `False` | - | Backup zones from Hetzner |
| `-w`, `--write` | `False` | - | Write zone files locally |
| `-C`, `--create-missing` | `False` | - | Create zones at Hetzner that are configured but not yet present |
| `--auth-api-token` | `""` | `DNSJINJA_AUTH_API_TOKEN` | Bearer token for Hetzner Cloud API |

### `explore_hetzner` Options

| Option | Default | Env Var | Description |
|--------|---------|---------|-------------|
| `-o`, `--output` | stdout | - | Output file for results |
| `--auth-api-token` | `""` | `DNSJINJA_AUTH_API_TOKEN` | Bearer token for Hetzner Cloud API |
| `--api-base` | `""` | `DNSJINJA_API_BASE` | Base URL of Hetzner Cloud API |

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
| `dns-api-base` | no | `https://api.hetzner.cloud/v1` | Base URL of the Hetzner Cloud API |

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

| Operation | hcloud Method |
|-----------|---------------|
| List zones | `client.zones.get_all()` |
| Import zone | `client.zones.import_zonefile(zone, zonefile)` |
| Export zone | `client.zones.export_zonefile(zone)` |

The `hcloud.Client` is initialised with the API token and optional `api_endpoint` (from `dns-api-base` config). The API token is created in the Hetzner Cloud Console (not the old dns.hetzner.com portal).

## Workflow

The main CLI executes three phases in order (each gated by its flag):

1. **Backup** (`-b`): Downloads current zones from Hetzner Cloud API, saves as `{zone-file}.{serial}` in `zone-backups/`
2. **Write** (`-w`): Renders Jinja2 templates for each domain, writes as `{zone-file}.{serial}` in `zone-files/`
3. **Upload** (`-u`): POSTs rendered zone content to Hetzner Cloud API for each domain

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

1. Create `include/<category>/<category>_<name>.inc` (e.g. `include/mail/mail_newprovider.inc`)
2. Reference it in domain config: `"mail": "newprovider"`

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

The `ENTRYPOINT` is `dnsjinja`. To run `explore_hetzner`, use `--entrypoint explore_hetzner`.

## Coding Conventions

- **Naming:** `snake_case` for functions/methods, `CamelCase` for classes
- **UI/comments language:** German (user-facing messages, comments, docstrings)
- **File paths:** `pathlib.Path` throughout for cross-platform compatibility
- **CLI:** Click framework with environment variable fallbacks
- **Error handling:** `sys.exit(1)` for fatal errors, custom `UploadError` for upload failures, batch operations continue on individual failures
- **Traceback suppression:** `sys.tracebacklimit = 0` in `__main__.py` for clean user output
- **No type hints** used in the codebase
- **No logging framework** - uses `print()` for all output
- **No tests** - no test suite exists

## Known Limitations & TODOs

- No unit/integration tests
- Templates stored in separate external repository
- German-only user interface
