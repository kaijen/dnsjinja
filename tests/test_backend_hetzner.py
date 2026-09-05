"""Tests des Hetzner-Backends gegen einen gemockten hcloud-Client.

Hier liegt das anbieterspezifische Wissen, das früher in test_unit.py stand:
die Action-Endpunkte, das protection-Feld und die Übersetzung der
hcloud-Ausnahmen.
"""
import hcloud
import pytest
from unittest.mock import MagicMock, patch

from dnsjinja.backends import (
    BackendError,
    BackendNotFoundError,
    BackendPermissionError,
    BackendUnavailableError,
    BackendValidationError,
    RRSet,
    RRSetChange,
    Zone,
)
from dnsjinja.backends.hetzner import HetznerBackend


@pytest.fixture
def backend():
    with patch('dnsjinja.backends.hetzner.Client') as client_cls:
        client = MagicMock()
        client_cls.return_value = client
        b = HetznerBackend(token='t')
        b.client = client
        yield b


@pytest.fixture
def zone():
    return Zone(name='example.com', zone_id='42', native=MagicMock())


def native_rrset(name, rtype, ttl, values, protected=False):
    r = MagicMock()
    r.name = name
    r.type = rtype
    r.ttl = ttl
    r.records = [MagicMock(value=v) for v in values]
    r.protection = {'change': True} if protected else None
    return r


class TestZonen:

    def test_list_zones_liefert_neutrale_zonen(self, backend):
        z = MagicMock(); z.name = 'example.com'; z.id = 42
        backend.client.zones.get_all.return_value = [z]

        zones = backend.list_zones()

        assert zones['example.com'].zone_id == '42'
        assert isinstance(zones['example.com'].zone_id, str)

    def test_create_zone_legt_primary_zone_an(self, backend):
        z = MagicMock(); z.name = 'neu.de'; z.id = 7
        backend.client.zones.create.return_value = MagicMock(zone=z)

        result = backend.create_zone('neu.de')

        backend.client.zones.create.assert_called_once_with(name='neu.de', mode='primary')
        assert result.name == 'neu.de'
        assert result.zone_id == '7'

    def test_export_zonefile_liefert_text(self, backend, zone):
        backend.client.zones.export_zonefile.return_value = MagicMock(
            zonefile='$ORIGIN example.com.\n'
        )
        assert backend.export_zonefile(zone).startswith('$ORIGIN')


class TestRRSetsLesen:

    def test_soa_wird_ausgefiltert(self, backend, zone):
        backend.client.zones.get_rrset_all.return_value = [
            native_rrset('@', 'SOA', 3600, ['ns.example. hostmaster.example. 1 2 3 4 5']),
            native_rrset('@', 'NS', 3600, ['ns.example.']),
        ]
        assert [r.rdtype for r in backend.list_rrsets(zone)] == ['NS']

    def test_protection_wird_übernommen(self, backend, zone):
        backend.client.zones.get_rrset_all.return_value = [
            native_rrset('www', 'A', 300, ['192.0.2.1'], protected=True)
        ]
        assert backend.list_rrsets(zone)[0].protected is True

    def test_werte_werden_sortiert(self, backend, zone):
        backend.client.zones.get_rrset_all.return_value = [
            native_rrset('www', 'A', 300, ['192.0.2.9', '192.0.2.1'])
        ]
        assert backend.list_rrsets(zone)[0].records == ('192.0.2.1', '192.0.2.9')


class TestÄnderungenAnwenden:

    def test_create_ruft_create_rrset(self, backend, zone):
        change = RRSetChange('create', 'www', 'A', ttl=300, records=['192.0.2.1'])

        result = backend.apply_changes(zone, [change])

        kwargs = backend.client.zones.create_rrset.call_args.kwargs
        assert kwargs['name'] == 'www'
        assert kwargs['type'] == 'A'
        assert kwargs['ttl'] == 300
        assert result.applied == 1
        assert result.atomic is False

    def test_update_mit_ttl_änderung_kostet_zwei_aufrufe(self, backend, zone):
        """RDATA und TTL liegen bei Hetzner auf getrennten Action-Endpunkten."""
        current = RRSet('www', 'A', 300, ('192.0.2.1',), handle=MagicMock())
        change = RRSetChange('update', 'www', 'A', ttl=600, records=['192.0.2.2'],
                             current_ttl=300, current_records=['192.0.2.1'],
                             current=current)

        backend.apply_changes(zone, [change])

        backend.client.zones.set_rrset_records.assert_called_once()
        backend.client.zones.change_rrset_ttl.assert_called_once_with(current.handle, 600)

    def test_update_ohne_ttl_änderung_kostet_einen_aufruf(self, backend, zone):
        current = RRSet('www', 'A', 300, ('192.0.2.1',), handle=MagicMock())
        change = RRSetChange('update', 'www', 'A', ttl=300, records=['192.0.2.2'],
                             current_ttl=300, current_records=['192.0.2.1'],
                             current=current)

        backend.apply_changes(zone, [change])

        backend.client.zones.set_rrset_records.assert_called_once()
        backend.client.zones.change_rrset_ttl.assert_not_called()

    def test_fehlgeschlagene_löschung_bricht_nicht_ab(self, backend, zone):
        current = RRSet('alt', 'A', 300, ('192.0.2.1',), handle=MagicMock())
        backend.client.zones.delete_rrset.side_effect = hcloud.APIException(
            code='protected', message='geschützt', details={}
        )
        changes = [
            RRSetChange('delete', 'alt', 'A', current=current),
            RRSetChange('create', 'neu', 'A', ttl=300, records=['192.0.2.2']),
        ]

        result = backend.apply_changes(zone, changes)

        assert result.applied == 1
        assert len(result.skipped) == 1
        assert result.skipped[0][0].name == 'alt'

    def test_fehler_beim_anlegen_wird_zu_backend_error(self, backend, zone):
        backend.client.zones.create_rrset.side_effect = hcloud.APIException(
            code='invalid_input', message='ungültig', details={}
        )
        change = RRSetChange('create', 'www', 'A', ttl=300, records=['nonsens'])

        with pytest.raises(BackendValidationError):
            backend.apply_changes(zone, [change])


class TestFehlerübersetzung:
    """Keine hcloud-Ausnahme darf das Backend verlassen."""

    @pytest.mark.parametrize('code,erwartet', [
        ('unauthorized', BackendError),
        ('forbidden', BackendPermissionError),
        ('not_found', BackendNotFoundError),
        ('invalid_input', BackendValidationError),
        ('irgendwas', BackendError),
    ])
    def test_api_exception_wird_übersetzt(self, backend, code, erwartet):
        backend.client.zones.get_all.side_effect = hcloud.APIException(
            code=code, message='x', details={}
        )
        with pytest.raises(erwartet):
            backend.list_zones()

    def test_netzwerkfehler_wird_übersetzt(self, backend):
        backend.client.zones.get_all.side_effect = OSError('Verbindung abgebrochen')
        with pytest.raises(BackendUnavailableError):
            backend.list_zones()
