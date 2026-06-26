"""Tests für das Hetzner-Plugin (Ticket #9).

Die hcloud-SDK ist gemockt; dies ist die einzige Stelle, an der noch ein
hcloud-Mock benötigt wird (Kern-Tests laufen über den FakeProvider).
"""
import hcloud
import pytest
from unittest.mock import MagicMock, patch

from dnsjinja.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    RRSet,
    Zone,
)
from dnsjinja.providers.hetzner import HetznerProvider


@pytest.fixture
def mock_client():
    with patch('dnsjinja.providers.hetzner.Client') as mock_class:
        client = MagicMock()
        mock_class.return_value = client
        yield client


@pytest.fixture
def provider(mock_client):
    return HetznerProvider(token='test-token')


def test_kein_token_wirft_auth_error():
    with pytest.raises(ProviderAuthError):
        HetznerProvider(token='')


def test_list_zones(provider, mock_client):
    z = MagicMock(); z.name = 'example.com'; z.id = 'zid-1'
    mock_client.zones.get_all.return_value = [z]

    zones = provider.list_zones()

    assert set(zones) == {'example.com'}
    assert zones['example.com'].id == 'zid-1'
    assert zones['example.com'].handle is z


def test_create_zone_nutzt_mode_primary(provider, mock_client):
    new_zone = MagicMock(); new_zone.name = 'neu.de'; new_zone.id = 'zid-neu'
    resp = MagicMock(); resp.zone = new_zone
    mock_client.zones.create.return_value = resp

    zone = provider.create_zone('neu.de')

    mock_client.zones.create.assert_called_once_with(name='neu.de', mode='primary')
    assert zone.id == 'zid-neu'


def test_get_rrsets_mapping_und_protection(provider, mock_client):
    rec1 = MagicMock(); rec1.value = '192.0.2.2'
    rec2 = MagicMock(); rec2.value = '192.0.2.1'
    rr = MagicMock()
    rr.name = '@'; rr.type = 'A'; rr.ttl = 300
    rr.records = [rec1, rec2]
    rr.protection = {'change': True}
    mock_client.zones.get_rrset_all.return_value = [rr]

    zone = Zone(name='example.com', id='zid', handle=object())
    result = provider.get_rrsets(zone)

    assert len(result) == 1
    got = result[0]
    assert got.name == '@' and got.type == 'A' and got.ttl == 300
    assert got.records == ['192.0.2.1', '192.0.2.2']  # sortiert
    assert got.protected is True
    assert got.handle is rr


def test_create_rrset_uebergibt_zonerecords(provider, mock_client):
    zone = Zone(name='example.com', id='zid', handle='zone-handle')

    provider.create_rrset(zone, '@', 'NS', 300, ['a.ns.example.', 'b.ns.example.'])

    args, kwargs = mock_client.zones.create_rrset.call_args
    assert args[0] == 'zone-handle'
    assert kwargs['name'] == '@' and kwargs['type'] == 'NS' and kwargs['ttl'] == 300
    assert [r.value for r in kwargs['records']] == ['a.ns.example.', 'b.ns.example.']


def test_set_rrset_records(provider, mock_client):
    zone = Zone(name='example.com', id='zid', handle=object())
    rrset = RRSet(name='@', type='A', ttl=300, records=[], handle='rr-handle')

    provider.set_rrset_records(zone, rrset, ['203.0.113.1'])

    args, _ = mock_client.zones.set_rrset_records.call_args
    assert args[0] == 'rr-handle'
    assert [r.value for r in args[1]] == ['203.0.113.1']


def test_set_rrset_ttl(provider, mock_client):
    zone = Zone(name='example.com', id='zid', handle=object())
    rrset = RRSet(name='@', type='A', ttl=300, records=[], handle='rr-handle')

    provider.set_rrset_ttl(zone, rrset, 600)

    mock_client.zones.change_rrset_ttl.assert_called_once_with('rr-handle', 600)


def test_delete_rrset(provider, mock_client):
    zone = Zone(name='example.com', id='zid', handle=object())
    rrset = RRSet(name='old', type='A', ttl=300, records=[], handle='rr-handle')

    provider.delete_rrset(zone, rrset)

    mock_client.zones.delete_rrset.assert_called_once_with('rr-handle')


def test_export_zonefile(provider, mock_client):
    resp = MagicMock(); resp.zonefile = '$ORIGIN example.com.\n'
    mock_client.zones.export_zonefile.return_value = resp
    zone = Zone(name='example.com', id='zid', handle='zone-handle')

    text = provider.export_zonefile(zone)

    mock_client.zones.export_zonefile.assert_called_once_with('zone-handle')
    assert text == '$ORIGIN example.com.\n'


# ---------------------------------------------------------------------------
# Fehler-Mapping
# ---------------------------------------------------------------------------

def test_api_exception_wird_zu_provider_error(provider, mock_client):
    mock_client.zones.get_all.side_effect = hcloud.APIException(
        code=500, message='boom', details={})
    with pytest.raises(ProviderError):
        provider.list_zones()


def test_403_wird_zu_auth_error(provider, mock_client):
    mock_client.zones.get_all.side_effect = hcloud.APIException(
        code='forbidden', message='nope', details={})
    with pytest.raises(ProviderAuthError):
        provider.list_zones()


def test_404_wird_zu_not_found(provider, mock_client):
    zone = Zone(name='example.com', id='zid', handle=object())
    mock_client.zones.get_rrset_all.side_effect = hcloud.APIException(
        code='not_found', message='weg', details={})
    with pytest.raises(ProviderNotFoundError):
        provider.get_rrsets(zone)
