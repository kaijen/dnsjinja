import os
import json
import pytest
from pathlib import Path


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: Integrationstests, die DNSJINJA_AUTH_API_TOKEN und DNSJINJA_TEST_DOMAIN benötigen",
    )


def _load_env():
    """Lädt .env-Dateien für Tests, falls vorhanden."""
    try:
        from dotenv import load_dotenv
        search_paths = [
            Path.home() / '.dnsjinja' / 'dnsjinja.env',
            Path.home() / 'dnsjinja.env',
            Path('.env'),
            Path('dnsjinja.env'),
        ]
        for p in search_paths:
            if p.exists():
                load_dotenv(p, override=False)
    except ImportError:
        pass


_load_env()


# ---------------------------------------------------------------------------
# Minimales Jinja2-Template für Tests
# ---------------------------------------------------------------------------

TEST_TEMPLATE = """\
$ORIGIN {{ domain }}.
$TTL 3600
@ IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. {{ soa_serial }} 86400 10800 3600000 3600
@ IN NS hydrogen.ns.hetzner.com.
@ IN NS oxygen.ns.hetzner.com.
@ IN NS helium.ns.hetzner.de.
"""


# ---------------------------------------------------------------------------
# Session-Fixtures für Zugangsdaten aus Umgebungsvariablen
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_token():
    """DNSJINJA_AUTH_API_TOKEN_TEST hat Vorrang (separates Hetzner-Projekt für Tests)."""
    return os.environ.get('DNSJINJA_AUTH_API_TOKEN_TEST') or os.environ.get('DNSJINJA_AUTH_API_TOKEN', '')


@pytest.fixture(scope="session")
def test_domain():
    return os.environ.get('DNSJINJA_TEST_DOMAIN', '')


@pytest.fixture(scope="session")
def require_api_token(api_token):
    if not api_token:
        pytest.skip("DNSJINJA_AUTH_API_TOKEN ist nicht gesetzt")
    return api_token


@pytest.fixture(scope="session")
def require_test_domain(test_domain):
    if not test_domain:
        pytest.skip("DNSJINJA_TEST_DOMAIN ist nicht gesetzt")
    return test_domain


# ---------------------------------------------------------------------------
# Verzeichnis- und Konfigurations-Fixtures
# ---------------------------------------------------------------------------

def make_config(domains: list[str]) -> dict:
    """Erstellt ein minimales config.json für die angegebenen Domains."""
    return {
        "global": {
            "zone-files": "zone-files",
            "zone-backups": "zone-backups",
            "templates": "templates",
            "name-servers": ["213.133.100.98", "88.198.229.192", "193.47.99.5"],
        },
        "domains": {domain: {"template": "test.tpl"} for domain in domains},
    }


def write_config(data_dir: Path, domains: list[str]) -> Path:
    """Schreibt config.json in data_dir und gibt den Pfad zurück."""
    config_path = data_dir / 'config' / 'config.json'
    config_path.write_text(json.dumps(make_config(domains)), encoding='utf-8')
    return config_path


@pytest.fixture
def data_dir(tmp_path):
    """Minimale Datenverzeichnis-Struktur für Tests."""
    (tmp_path / 'config').mkdir()
    (tmp_path / 'templates').mkdir()
    (tmp_path / 'zone-files').mkdir()
    (tmp_path / 'zone-backups').mkdir()
    (tmp_path / 'templates' / 'test.tpl').write_text(TEST_TEMPLATE, encoding='utf-8')
    return tmp_path


@pytest.fixture
def config_file(data_dir):
    """Config mit example.com als Testdomain."""
    return write_config(data_dir, ['example.com'])


# ---------------------------------------------------------------------------
# Mock-Fixtures für Unit-Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_zone():
    """Gemocktes BoundZone-Objekt für example.com."""
    from unittest.mock import MagicMock
    zone = MagicMock()
    zone.name = 'example.com'
    zone.id = 'test-zone-id-123'
    return zone


@pytest.fixture
def mock_client(mock_zone):
    """Vollständig gemockter hcloud.Client."""
    from unittest.mock import MagicMock, patch

    export_resp = MagicMock()
    export_resp.zonefile = '$ORIGIN example.com.\n$TTL 3600\n'

    with patch('dnsjinja.dnsjinja.Client') as mock_class:
        client = MagicMock()
        mock_class.return_value = client
        client.zones.get_all.return_value = [mock_zone]
        client.zones.export_zonefile.return_value = export_resp
        client.zones.get_rrset_all.return_value = []
        yield client


@pytest.fixture
def mock_dns_resolver():
    """Gemockter DNS-Resolver, der einen festen SOA-Zähler zurückgibt."""
    from unittest.mock import MagicMock, patch

    with patch('dns.resolver.Resolver') as mock_class:
        resolver = MagicMock()
        mock_class.return_value = resolver
        soa = MagicMock()
        soa.serial = 2026020101
        resolver.resolve.return_value = [soa]
        yield resolver
