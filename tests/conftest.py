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
# FakeProvider – provider-neutraler In-Memory-Ersatz (Tickets #9/#10)
# ---------------------------------------------------------------------------

from dnsjinja.providers.base import DnsProvider, ProviderError, RRSet, Zone


class FakeProvider(DnsProvider):
    """In-Memory-`DnsProvider` für Offline-Tests ohne hcloud.

    Zeichnet alle mutierenden Aufrufe in `self.calls` auf und erlaubt das
    gezielte Auslösen von `ProviderError` pro Methode (`fail`) oder pro Zone
    (`fail_zones`).
    """

    name = "fake"

    def __init__(self, *, token=None, api_base=None, options=None,
                 zones=None, rrsets=None, export_text=None,
                 supports_export=True, fail=None, fail_zones=None):
        self.token = token
        self.api_base = api_base
        self.options = options or {}
        self._zones = {n: Zone(name=n, id=f'id-{n}', handle=object()) for n in (zones or [])}
        self._rrsets = {k: list(v) for k, v in (rrsets or {}).items()}
        self._export_text = export_text if export_text is not None else '$ORIGIN example.com.\n$TTL 3600\n'
        self._supports_export = supports_export
        self.fail = dict(fail or {})
        self.fail_zones = set(fail_zones or [])
        self.calls = []

    def _maybe_fail(self, method, zone_name=None):
        if method in self.fail:
            raise self.fail[method]
        if zone_name is not None and zone_name in self.fail_zones:
            raise ProviderError(f"Fake-Fehler für Zone {zone_name}")

    def list_zones(self):
        self._maybe_fail('list_zones')
        self.calls.append(('list_zones',))
        return dict(self._zones)

    def create_zone(self, name):
        self._maybe_fail('create_zone')
        z = Zone(name=name, id=f'id-{name}', handle=object())
        self._zones[name] = z
        self.calls.append(('create_zone', name))
        return z

    def get_rrsets(self, zone):
        self._maybe_fail('get_rrsets', zone.name)
        self.calls.append(('get_rrsets', zone.name))
        return list(self._rrsets.get(zone.name, []))

    def create_rrset(self, zone, name, type, ttl, records):
        self._maybe_fail('create_rrset')
        self.calls.append(('create_rrset', zone.name, name, type, ttl, list(records)))

    def set_rrset_records(self, zone, rrset, records):
        self._maybe_fail('set_rrset_records')
        self.calls.append(('set_rrset_records', zone.name, rrset.name, rrset.type, list(records)))

    def set_rrset_ttl(self, zone, rrset, ttl):
        self._maybe_fail('set_rrset_ttl')
        self.calls.append(('set_rrset_ttl', zone.name, rrset.name, rrset.type, ttl))

    def delete_rrset(self, zone, rrset):
        self._maybe_fail('delete_rrset')
        self.calls.append(('delete_rrset', zone.name, rrset.name, rrset.type))

    def supports_zonefile_export(self):
        return self._supports_export

    def export_zonefile(self, zone):
        self._maybe_fail('export_zonefile', zone.name)
        self.calls.append(('export_zonefile', zone.name))
        return self._export_text

    # -- Test-Hilfen -------------------------------------------------------

    def calls_of(self, method):
        return [c for c in self.calls if c[0] == method]


def install_provider_loader(monkeypatch, provider_or_factory):
    """Patcht die Registry so, dass `load_provider` den/die Fake liefert.

    `provider_or_factory` ist entweder eine einzelne `DnsProvider`-Instanz
    (für Single-Provider-Tests) oder eine Funktion ``plugin -> DnsProvider``
    (für Multiprovider-Tests).
    """
    if callable(provider_or_factory) and not isinstance(provider_or_factory, DnsProvider):
        def _loader(plugin, *, token, api_base=None, options=None):
            return provider_or_factory(plugin)
    else:
        def _loader(plugin, *, token, api_base=None, options=None):
            return provider_or_factory
    monkeypatch.setattr('dnsjinja.providers.registry.load_provider', _loader)


@pytest.fixture
def make_dj(data_dir, mock_dns_resolver, monkeypatch):
    """Factory: DNSJinja mit injiziertem FakeProvider (oder Provider-Factory)."""
    from dnsjinja.dnsjinja import DNSJinja

    def _make(config_path, provider=None, **kwargs):
        if provider is None:
            provider = FakeProvider(zones=['example.com'])
        install_provider_loader(monkeypatch, provider)
        return DNSJinja(
            datadir=str(data_dir),
            config_file=str(config_path),
            auth_api_token='test-token-unit',
            **kwargs,
        )

    return _make


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


# ---------------------------------------------------------------------------
# testdata/ – eingecheckte Test-Fixture (synthetische Templates)
# ---------------------------------------------------------------------------

TESTDATA_DIR = Path(__file__).resolve().parent.parent / 'testdata'


@pytest.fixture(scope="session")
def testdata_dir():
    """Absoluter Pfad zum eingecheckten testdata/-Verzeichnis."""
    assert TESTDATA_DIR.is_dir(), f"testdata-Verzeichnis fehlt: {TESTDATA_DIR}"
    return TESTDATA_DIR


def make_testdata_config(domains_cfg: dict) -> dict:
    """config.json-Struktur mit den testdata-Templates und beliebigen Domains."""
    return {
        "global": {
            "zone-files": "zone-files",
            "zone-backups": "zone-backups",
            "templates": "templates",
            "name-servers": ["213.133.100.98", "88.198.229.192", "193.47.99.5"],
        },
        "domains": domains_cfg,
    }


@pytest.fixture
def build_dj(testdata_dir, tmp_path, mock_dns_resolver, monkeypatch):
    """Factory: baut eine DNSJinja-Instanz gegen testdata/-Templates.

    Der DNS-Provider ist ein In-Memory-`FakeProvider`, dessen `list_zones()`
    genau die konfigurierten Domains liefert, damit _prepare_zones sie nicht
    verwirft. Der DNS-Resolver ist gemockt. Reines Rendering – es werden keine
    Zone-Files geschrieben.
    """
    from dnsjinja.dnsjinja import DNSJinja

    counter = {'n': 0}

    def _build(domains_cfg: dict, **kwargs):
        cfg = make_testdata_config(domains_cfg)
        cfg_path = tmp_path / f'config-{counter["n"]}.json'
        counter['n'] += 1
        cfg_path.write_text(json.dumps(cfg), encoding='utf-8')

        provider = FakeProvider(zones=list(domains_cfg.keys()))
        install_provider_loader(monkeypatch, provider)
        return DNSJinja(
            datadir=str(testdata_dir),
            config_file=str(cfg_path),
            auth_api_token='test-token',
            **kwargs,
        )

    return _build
