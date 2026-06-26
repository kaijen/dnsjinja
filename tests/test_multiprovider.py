"""Tests für den Multiprovider-Betrieb (Ticket #10).

Zwei FakeProvider mit unterschiedlichen Zonenbeständen; Domains werden je nach
config-`provider`-Feld geroutet. Keine echten API-Aufrufe.
"""
import json

import pytest

from dnsjinja.dnsjinja import DNSJinja
from dnsjinja.providers.base import ProviderError
from tests.conftest import FakeProvider, install_provider_loader


def _write_multiprovider_config(data_dir, *, providers, domains, default_provider=None):
    glob = {
        "zone-files": "zone-files",
        "zone-backups": "zone-backups",
        "templates": "templates",
        "name-servers": ["213.133.100.98"],
        "providers": providers,
    }
    if default_provider is not None:
        glob["default-provider"] = default_provider
    cfg = {"global": glob, "domains": domains}
    path = data_dir / 'config' / 'config.json'
    path.write_text(json.dumps(cfg), encoding='utf-8')
    return path


@pytest.fixture
def two_providers():
    """Zwei FakeProvider; p1 kennt a.example, p2 kennt b.example."""
    p1 = FakeProvider(zones=['a.example'])
    p2 = FakeProvider(zones=['b.example'])
    p1.name = 'p1'
    p2.name = 'p2'
    return p1, p2


@pytest.fixture
def build_multi(data_dir, mock_dns_resolver, monkeypatch):
    def _build(providers_map, *, providers, domains, default_provider=None, **kwargs):
        path = _write_multiprovider_config(
            data_dir, providers=providers, domains=domains,
            default_provider=default_provider)
        install_provider_loader(monkeypatch, lambda plugin: providers_map[plugin])
        return DNSJinja(
            datadir=str(data_dir), config_file=str(path),
            auth_api_token='legacy-token', **kwargs)
    return _build


def test_domains_werden_pro_provider_geroutet(build_multi, two_providers):
    p1, p2 = two_providers
    dj = build_multi(
        {'plugin1': p1, 'plugin2': p2},
        providers={'p1': {'plugin': 'plugin1'}, 'p2': {'plugin': 'plugin2'}},
        default_provider='p1',
        domains={
            'a.example': {'template': 'test.tpl'},
            'b.example': {'template': 'test.tpl', 'provider': 'p2'},
        },
    )

    assert dj._provider_for['a.example'] is p1
    assert dj._provider_for['b.example'] is p2


def test_list_zones_pro_provider_genau_einmal(build_multi, two_providers):
    """Jeder Provider wird einmal nach seinen Zonen gefragt (Gruppierung)."""
    p1, p2 = two_providers
    build_multi(
        {'plugin1': p1, 'plugin2': p2},
        providers={'p1': {'plugin': 'plugin1'}, 'p2': {'plugin': 'plugin2'}},
        default_provider='p1',
        domains={
            'a.example': {'template': 'test.tpl'},
            'b.example': {'template': 'test.tpl', 'provider': 'p2'},
        },
    )

    assert len(p1.calls_of('list_zones')) == 1
    assert len(p2.calls_of('list_zones')) == 1


def test_warnung_ist_provider_lokal(build_multi, two_providers, capsys):
    """p1 darf b.example NICHT als 'nicht konfiguriert' melden (gehört zu p2)."""
    p1, p2 = two_providers
    build_multi(
        {'plugin1': p1, 'plugin2': p2},
        providers={'p1': {'plugin': 'plugin1'}, 'p2': {'plugin': 'plugin2'}},
        default_provider='p1',
        domains={
            'a.example': {'template': 'test.tpl'},
            'b.example': {'template': 'test.tpl', 'provider': 'p2'},
        },
    )

    out = capsys.readouterr().out
    # Keine falsche "nicht konfiguriert"-Warnung über Provider-Grenzen hinweg.
    assert 'bitte prüfen' not in out


def test_fehler_isolierung(build_multi, two_providers, capsys):
    """Fällt p2 aus, bleibt a.example (p1) trotzdem voll nutzbar."""
    p1, p2 = two_providers
    p2.fail = {'list_zones': ProviderError('p2 down')}
    dj = build_multi(
        {'plugin1': p1, 'plugin2': p2},
        providers={'p1': {'plugin': 'plugin1'}, 'p2': {'plugin': 'plugin2'}},
        default_provider='p1',
        domains={
            'a.example': {'template': 'test.tpl'},
            'b.example': {'template': 'test.tpl', 'provider': 'p2'},
        },
    )

    assert 'a.example' in dj._provider_for
    assert 'b.example' not in dj.config['domains']
    assert 'nicht verfügbar' in capsys.readouterr().out


def test_zwei_accounts_gleiches_plugin(build_multi):
    """Zwei benannte Provider mit demselben Plugin sind getrennte Instanzen."""
    pa = FakeProvider(zones=['a.example']); pa.name = 'acc-a'
    pb = FakeProvider(zones=['b.example']); pb.name = 'acc-b'
    # Loader dispatcht über token-env-unterschiedliche Definitionen via plugin-Key.
    providers_map = {'hetzner-a': pa, 'hetzner-b': pb}
    dj = build_multi(
        providers_map,
        providers={
            'acc-a': {'plugin': 'hetzner-a'},
            'acc-b': {'plugin': 'hetzner-b'},
        },
        domains={
            'a.example': {'template': 'test.tpl', 'provider': 'acc-a'},
            'b.example': {'template': 'test.tpl', 'provider': 'acc-b'},
        },
    )

    assert dj._provider_for['a.example'] is pa
    assert dj._provider_for['b.example'] is pb


# ---------------------------------------------------------------------------
# Config-Validierung der Provider-Referenzen
# ---------------------------------------------------------------------------

class TestProviderRefValidierung:

    def _build_invalid(self, data_dir, mock_dns_resolver, **cfg_kwargs):
        path = _write_multiprovider_config(data_dir, **cfg_kwargs)
        with pytest.raises(SystemExit):
            DNSJinja(datadir=str(data_dir), config_file=str(path),
                     auth_api_token='t')

    def test_unbekannter_domain_provider(self, data_dir, mock_dns_resolver):
        self._build_invalid(
            data_dir, mock_dns_resolver,
            providers={'p1': {'plugin': 'plugin1'}},
            default_provider='p1',
            domains={'a.example': {'template': 'test.tpl', 'provider': 'gibtsnicht'}},
        )

    def test_unbekannter_default_provider(self, data_dir, mock_dns_resolver):
        self._build_invalid(
            data_dir, mock_dns_resolver,
            providers={'p1': {'plugin': 'plugin1'}},
            default_provider='nope',
            domains={'a.example': {'template': 'test.tpl'}},
        )

    def test_domain_provider_ohne_providers_block(self, data_dir, mock_dns_resolver):
        # provider-Feld an der Domain, aber kein global.providers
        path = data_dir / 'config' / 'config.json'
        path.write_text(json.dumps({
            "global": {
                "zone-files": "zone-files", "zone-backups": "zone-backups",
                "templates": "templates", "name-servers": ["213.133.100.98"],
            },
            "domains": {"a.example": {"template": "test.tpl", "provider": "x"}},
        }), encoding='utf-8')
        with pytest.raises(SystemExit):
            DNSJinja(datadir=str(data_dir), config_file=str(path), auth_api_token='t')
