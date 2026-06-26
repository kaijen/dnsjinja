"""Tests für die Provider-Registry / Plugin-Discovery (Ticket #9)."""
import pytest

from dnsjinja.providers import available_plugins, load_provider
from dnsjinja.providers.base import DnsProvider, ProviderError
from dnsjinja.providers.hetzner import HetznerProvider


def test_builtin_hetzner_ist_verfuegbar():
    assert 'hetzner' in available_plugins()


def test_load_builtin_hetzner():
    provider = load_provider('hetzner', token='dummy-token')
    assert isinstance(provider, HetznerProvider)
    assert provider.name == 'hetzner'


def test_load_per_import_pfad():
    """Ein Provider lässt sich auch über 'modul:Klasse' laden (Override)."""
    provider = load_provider(
        'dnsjinja.providers.hetzner:HetznerProvider', token='dummy-token')
    assert isinstance(provider, HetznerProvider)


def test_unbekanntes_plugin_wirft_provider_error():
    with pytest.raises(ProviderError) as exc:
        load_provider('gibtsnicht', token='x')
    assert 'gibtsnicht' in str(exc.value)


def test_geladener_provider_ist_dnsprovider():
    provider = load_provider('hetzner', token='dummy-token')
    assert isinstance(provider, DnsProvider)
