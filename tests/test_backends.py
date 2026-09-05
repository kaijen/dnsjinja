"""Tests für die Backend-Registry und den Plugin-Vertrag."""
import pytest

from dnsjinja.backends import (
    BackendCapabilities,
    DNSBackend,
    UnknownBackendError,
    available_backends,
    create_backend,
    get_backend_class,
)
from dnsjinja.backends import registry


class _Plugin(DNSBackend):
    """Minimales Fremd-Backend für die Entry-Point-Tests."""
    name = 'plugin'
    default_api_base = 'https://plugin.invalid'
    capabilities = BackendCapabilities()

    def list_zones(self): return {}
    def create_zone(self, domain): raise NotImplementedError
    def export_zonefile(self, zone): raise NotImplementedError
    def list_rrsets(self, zone): return []
    def apply_changes(self, zone, changes): raise NotImplementedError


class _FakeEntryPoint:
    def __init__(self, name, loader, value='paket:Klasse', dist_name='fremdpaket'):
        self.name = name
        self.value = value
        self._loader = loader
        self.dist = type('Dist', (), {'name': dist_name})()

    def load(self):
        return self._loader()


@pytest.fixture
def patch_entry_points(monkeypatch):
    def _patch(*eps):
        monkeypatch.setattr(registry, '_iter_entry_points', lambda: list(eps))
    return _patch


class TestEingebauteBackends:

    def test_hetzner_ist_auflösbar(self):
        from dnsjinja.backends.hetzner import HetznerBackend
        assert get_backend_class('hetzner') is HetznerBackend

    def test_desec_ist_auflösbar(self):
        from dnsjinja.backends.desec import DesecBackend
        assert get_backend_class('desec') is DesecBackend

    @pytest.mark.parametrize('name', ['hetzner', 'desec'])
    def test_capabilities_sind_vollständig(self, name):
        caps = get_backend_class(name).capabilities
        assert caps.min_ttl > 0
        assert 'SOA' in caps.readonly_rdtypes

    def test_beide_werden_gelistet(self):
        verfuegbar = available_backends()
        assert verfuegbar['hetzner'] == 'builtin'
        assert verfuegbar['desec'] == 'builtin'

    def test_create_backend_liefert_instanz(self):
        backend = create_backend('desec', token='t')
        assert backend.name == 'desec'
        assert backend.api_base == 'https://desec.io/api/v1'
        backend.close()

    def test_eigene_api_base_gewinnt(self):
        backend = create_backend('desec', token='t', api_base='https://dns.example/api/v1/')
        assert backend.api_base == 'https://dns.example/api/v1'
        backend.close()


class TestPluginAuflösung:

    def test_entry_point_backend_wird_gefunden(self, patch_entry_points):
        patch_entry_points(_FakeEntryPoint('plugin', lambda: _Plugin))
        assert get_backend_class('plugin') is _Plugin

    def test_entry_point_wird_gelistet(self, patch_entry_points):
        patch_entry_points(_FakeEntryPoint('plugin', lambda: _Plugin))
        assert available_backends()['plugin'] == 'fremdpaket'

    def test_eingebautes_backend_gewinnt_bei_namensgleichheit(self, patch_entry_points):
        from dnsjinja.backends.hetzner import HetznerBackend
        patch_entry_points(_FakeEntryPoint('hetzner', lambda: _Plugin))
        assert get_backend_class('hetzner') is HetznerBackend
        assert available_backends()['hetzner'] == 'builtin'

    def test_defektes_plugin_bricht_den_lauf_nicht_ab(self, patch_entry_points):
        def kaputt():
            raise ImportError('fehlende Abhängigkeit')

        patch_entry_points(_FakeEntryPoint('kaputt', kaputt))
        # Ein defektes Plugin darf die Auflösung anderer Namen nicht verhindern.
        assert get_backend_class('hetzner') is not None
        with pytest.raises(UnknownBackendError):
            get_backend_class('kaputt')

    def test_plugin_ohne_dnsbackend_basis_wird_ignoriert(self, patch_entry_points):
        patch_entry_points(_FakeEntryPoint('fremd', lambda: dict))
        with pytest.raises(UnknownBackendError):
            get_backend_class('fremd')

    def test_unbekannter_name_nennt_die_verfügbaren(self):
        with pytest.raises(UnknownBackendError) as excinfo:
            get_backend_class('gibtsnicht')
        meldung = str(excinfo.value)
        assert 'hetzner' in meldung and 'desec' in meldung

    def test_eigener_entry_point_erzeugt_keine_warnung(self, patch_entry_points, caplog):
        """Die Builtins stehen absichtlich auch als Entry-Point in pyproject.toml."""
        patch_entry_points(_FakeEntryPoint(
            'hetzner', lambda: _Plugin,
            value='dnsjinja.backends.hetzner:HetznerBackend',
        ))
        with caplog.at_level('WARNING'):
            available_backends()
        assert caplog.records == []

    def test_fremdes_paket_unter_gleichem_namen_wird_gemeldet(self, patch_entry_points, caplog):
        patch_entry_points(_FakeEntryPoint('hetzner', lambda: _Plugin, value='fremd:Backend'))
        with caplog.at_level('WARNING'):
            available_backends()
        assert any('ignoriert' in r.message for r in caplog.records)
