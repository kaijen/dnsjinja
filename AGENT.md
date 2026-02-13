# AGENT.md - DNSJinja

## Project Overview

DNSJinja is a Python CLI tool for managing DNS zones at Hetzner. It uses Jinja2 templates to generate BIND9-compatible zone files and deploys them to Hetzner DNS via their REST API.

- **Language:** Python 3.10+
- **License:** MIT
- **Package name:** `dnsjinja-kaijen`
- **Author:** Kai Jendrian
- **Repository:** https://github.com/kaijen/dnsjinja

## Architecture & Directory Structure

```
DNSJinja/                                    # Tool repository
├── src/dnsjinja/                            # Main package source
│   ├── __init__.py                          # Package exports (DNSJinja, main, explore_main, exit_on_error)
│   ├── __main__.py                          # Entry point for `python -m dnsjinja`
│   ├── dnsjinja.py                          # Core class, CLI, and API operations (~260 lines)
│   ├── dnsjinja_config_schema.py            # JSON Schema (Draft 7) for config validation (~180 lines)
│   ├── explore_hetzner.py                   # Hetzner zone discovery utility (~60 lines)
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

- **`__init__(upload, backup, write_zone, datadir, config_file, auth_api_token)`** - Loads config, validates schema, sets up Jinja2 environment, prepares zones
- **`_prepare_zones()`** - Syncs configured domains with Hetzner API zones
- **`_get_zone_serial(domain)`** - Queries SOA serial from Hetzner nameservers via dnspython
- **`_new_zone_serial(domain)`** - Generates SOA serial in `YYYYMMDD##` format (auto-incrementing counter)
- **`_create_zone_data()`** - Renders all Jinja2 templates into zone file content
- **`write_zone_files()`** - Writes rendered zones to local files as `{domain}.zone.{serial}`
- **`upload_zone(domain)` / `upload_zones()`** - POSTs zone data to Hetzner import API
- **`backup_zone(domain)` / `backup_zones()`** - GETs zone data from Hetzner export API

Custom exception: `UploadError` - raised on upload failure (HTTP != 200), writes exit code 254 to temp file.

CLI function `run()` uses Click with options for `--datadir`, `--config`, `--upload`, `--backup`, `--write`, `--auth-api-token`.

### `dnsjinja_config_schema.py` - Config Schema

Defines `DNSJINJA_JSON_SCHEMA` (JSON Schema Draft 7) with two sections:
- **`global`**: `zone-files`, `zone-backups`, `templates` (directories), `dns-upload-api`, `dns-download-api`, `dns-zones-api` (URIs), `name-servers` (IPv4 array)
- **`domains`**: Object keyed by domain name, each with `template` (required), `zone-id` (required), `zone-file` (optional)

Note: `zone-id` and `zone-file` are auto-populated by `_prepare_zones()` from the Hetzner API at runtime.

### `explore_hetzner.py` - Zone Discovery

`ExploreHetzner` class fetches all zones from Hetzner API and outputs a JSON config template. Useful for initial project setup.

### `myloadenv.py` - Environment Loader

`load_env()` searches multiple platform-aware paths for `.env` and `{module}.env` files using `appdirs` and `python-dotenv`. Paths include `~/`, `~/.config/`, `~/.dnsjinja/`, user config dir, and CWD.

### `exit_on_error.py` - Exit Code Handler

Reads exit code from `{tempdir}/dnsjinja.exit.txt` and calls `sys.exit()` with that code. Used to propagate error codes across process boundaries (especially on Windows).

## Dependencies

| Package | Purpose |
|---------|---------|
| Jinja2 | Template rendering for zone files |
| requests | HTTP client for Hetzner REST API |
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
| `--auth-api-token` | `""` | `DNSJINJA_AUTH_API_TOKEN` | Hetzner API token |

### `explore_hetzner` Options

| Option | Default | Env Var | Description |
|--------|---------|---------|-------------|
| `-o`, `--output` | stdout | - | Output file for results |
| `--auth-api-token` | `""` | `DNSJINJA_AUTH_API_TOKEN` | Hetzner API token |

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

### Example

```json
{
  "global": {
    "zone-files": "zone-files",
    "zone-backups": "zone-backups",
    "templates": "templates",
    "dns-upload-api": "https://dns.hetzner.com/api/v1/zones/{ZoneID}/import",
    "dns-download-api": "https://dns.hetzner.com/api/v1/zones/{ZoneID}/export",
    "dns-zones-api": "https://dns.hetzner.com/api/v1/zones",
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

## Workflow

The main CLI executes three phases in order (each gated by its flag):

1. **Backup** (`-b`): Downloads current zones from Hetzner export API, saves as `{zone-file}.{serial}` in `zone-backups/`
2. **Write** (`-w`): Renders Jinja2 templates for each domain, writes as `{zone-file}.{serial}` in `zone-files/`
3. **Upload** (`-u`): POSTs rendered zone content to Hetzner import API for each domain

On initialization, `_prepare_zones()` always runs to sync configured domains against Hetzner's zone list and warn about mismatches.

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
- No Docker support (planned)
- Planned migration to Hetzner Cloud API (from current DNS API)
- Templates stored in separate external repository
- German-only user interface
