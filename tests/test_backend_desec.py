"""Tests des deSEC-Backends auf HTTP-Ebene, ohne Netz."""
import pytest
import requests
import requests_mock

from dnsjinja.backends import (
    BackendAuthError,
    BackendNotFoundError,
    BackendPermissionError,
    BackendRateLimitError,
    BackendUnavailableError,
    BackendValidationError,
    RRSet,
    RRSetChange,
    Zone,
)
from dnsjinja.backends.desec import DesecBackend

API = 'https://desec.io/api/v1'
ZONE = Zone(name='example.com', zone_id='example.com')


@pytest.fixture
def backend():
    b = DesecBackend(token='geheim')
    yield b
    b.close()


@pytest.fixture
def http():
    with requests_mock.Mocker() as m:
        yield m


class TestAuthentifizierung:

    def test_header_ist_token_nicht_bearer(self, backend, http):
        """deSEC verlangt 'Token', nicht 'Bearer' – eine häufige Verwechslung."""
        http.get(f'{API}/domains/', json=[])

        backend.list_zones()

        assert http.last_request.headers['Authorization'] == 'Token geheim'


class TestZonen:

    def test_list_zones_liest_minimum_ttl(self, backend, http):
        http.get(f'{API}/domains/', json=[
            {'name': 'example.com', 'minimum_ttl': 3600},
        ])

        zones = backend.list_zones()

        assert zones['example.com'].zone_id == 'example.com'
        assert zones['example.com'].min_ttl == 3600

    def test_zonen_mindest_ttl_wirkt_auf_effective_min_ttl(self, backend, http):
        http.get(f'{API}/domains/', json=[
            {'name': 'example.com', 'minimum_ttl': 7200},
        ])
        zone = backend.list_zones()['example.com']

        assert backend.effective_min_ttl(zone) == 7200

    def test_create_zone_sendet_nur_den_namen(self, backend, http):
        http.post(f'{API}/domains/', json={'name': 'neu.de', 'minimum_ttl': 3600},
                  status_code=201)

        result = backend.create_zone('neu.de')

        assert http.last_request.json() == {'name': 'neu.de'}
        assert result.name == 'neu.de'

    def test_export_zonefile(self, backend, http):
        http.get(f'{API}/domains/example.com/zonefile/', text='$ORIGIN example.com.\n')
        assert backend.export_zonefile(ZONE).startswith('$ORIGIN')

    def test_zonefile_import_in_bestehende_zone_wird_nicht_angeboten(self, backend):
        """Ein Restore aus dem Backup ist bei deSEC kein Routinevorgang."""
        assert backend.capabilities.supports_zonefile_import is False
        assert backend.capabilities.supports_zonefile_import_on_create is True


class TestRRSetsLesen:

    def test_apex_kommt_als_at_zeichen_zurück(self, backend, http):
        http.get(f'{API}/domains/example.com/rrsets/', json=[
            {'subname': '', 'type': 'NS', 'ttl': 3600, 'records': ['ns.example.']},
        ])

        (rrset,) = backend.list_rrsets(ZONE)

        assert rrset.name == '@'

    def test_subname_bleibt_erhalten(self, backend, http):
        http.get(f'{API}/domains/example.com/rrsets/', json=[
            {'subname': 'www', 'type': 'A', 'ttl': 3600, 'records': ['192.0.2.1']},
        ])
        assert backend.list_rrsets(ZONE)[0].name == 'www'

    @pytest.mark.parametrize('rdtype', ['SOA', 'DNSKEY', 'DS', 'RRSIG', 'NSEC3PARAM'])
    def test_verwaltete_typen_werden_ausgefiltert(self, backend, http, rdtype):
        """Sonst plant dnsjinja für jeden DNSSEC-Record eine Löschung."""
        http.get(f'{API}/domains/example.com/rrsets/', json=[
            {'subname': '', 'type': rdtype, 'ttl': 3600, 'records': ['x']},
            {'subname': 'www', 'type': 'A', 'ttl': 3600, 'records': ['192.0.2.1']},
        ])

        assert [r.rdtype for r in backend.list_rrsets(ZONE)] == ['A']

    def test_cursor_paginierung_wird_zusammengeführt(self, backend, http):
        seite2 = f'{API}/domains/example.com/rrsets/?cursor=zweite'
        http.get(
            f'{API}/domains/example.com/rrsets/',
            [
                {
                    'json': [{'subname': 'a', 'type': 'A', 'ttl': 3600,
                              'records': ['192.0.2.1']}],
                    'headers': {'Link': f'<{seite2}>; rel="next"'},
                },
                {
                    'json': [{'subname': 'b', 'type': 'A', 'ttl': 3600,
                              'records': ['192.0.2.2']}],
                },
            ],
        )

        namen = [r.name for r in backend.list_rrsets(ZONE)]

        assert namen == ['a', 'b']


class TestÄnderungenAnwenden:

    def _patch_body(self, http):
        return http.last_request.json()

    def test_ein_plan_wird_zu_genau_einem_request(self, backend, http):
        http.patch(f'{API}/domains/example.com/rrsets/', json=[])
        current = RRSet('alt', 'A', 3600, ('192.0.2.9',))
        changes = [
            RRSetChange('create', 'www', 'A', ttl=3600, records=['192.0.2.1']),
            RRSetChange('update', 'mail', 'A', ttl=3600, records=['192.0.2.2'],
                        current_ttl=3600, current_records=['192.0.2.3'],
                        current=RRSet('mail', 'A', 3600, ('192.0.2.3',))),
            RRSetChange('delete', 'alt', 'A', current=current),
        ]

        result = backend.apply_changes(ZONE, changes)

        assert http.call_count == 1
        assert result.applied == 3
        assert result.atomic is True

    def test_apex_wird_zum_leeren_string(self, backend, http):
        """Im Bulk-Body ist der Apex '', nicht '@' – '@' ergäbe einen Subname."""
        http.patch(f'{API}/domains/example.com/rrsets/', json=[])

        backend.apply_changes(ZONE, [
            RRSetChange('create', '@', 'NS', ttl=3600, records=['ns.example.'])
        ])

        assert self._patch_body(http)[0]['subname'] == ''

    def test_löschung_sendet_leere_werteliste(self, backend, http):
        http.patch(f'{API}/domains/example.com/rrsets/', json=[])
        current = RRSet('alt', 'A', 3600, ('192.0.2.1',))

        backend.apply_changes(ZONE, [RRSetChange('delete', 'alt', 'A', current=current)])

        eintrag = self._patch_body(http)[0]
        assert eintrag['records'] == []
        assert eintrag['subname'] == 'alt'

    def test_leerer_plan_löst_keinen_request_aus(self, backend, http):
        assert backend.apply_changes(ZONE, []).applied == 0
        assert http.call_count == 0

    def test_apex_round_trip(self, backend, http):
        """Was gelesen wurde, muss unverändert wieder geschrieben werden können."""
        http.get(f'{API}/domains/example.com/rrsets/', json=[
            {'subname': '', 'type': 'NS', 'ttl': 3600, 'records': ['ns.example.']},
        ])
        http.patch(f'{API}/domains/example.com/rrsets/', json=[])

        (gelesen,) = backend.list_rrsets(ZONE)
        backend.apply_changes(ZONE, [
            RRSetChange('update', gelesen.name, gelesen.rdtype, ttl=gelesen.ttl,
                        records=list(gelesen.records), current=gelesen)
        ])

        assert self._patch_body(http)[0]['subname'] == ''


class TestRatenlimit:

    def test_429_wird_nach_retry_after_wiederholt(self, backend, http, monkeypatch):
        geschlafen = []
        monkeypatch.setattr('dnsjinja.backends.desec.time.sleep', geschlafen.append)
        http.get(f'{API}/domains/', [
            {'status_code': 429, 'headers': {'Retry-After': '5'}, 'json': {}},
            {'json': [{'name': 'example.com', 'minimum_ttl': 3600}]},
        ])

        zones = backend.list_zones()

        assert geschlafen == [5.0]
        assert list(zones) == ['example.com']

    def test_dauerhaftes_429_wirft_ratelimit_fehler(self, backend, http, monkeypatch):
        monkeypatch.setattr('dnsjinja.backends.desec.time.sleep', lambda s: None)
        http.get(f'{API}/domains/', status_code=429,
                 headers={'Retry-After': '2'}, json={})

        with pytest.raises(BackendRateLimitError) as excinfo:
            backend.list_zones()

        assert excinfo.value.retry_after == 2.0


class TestFehlerübersetzung:

    @pytest.mark.parametrize('status,erwartet', [
        (401, BackendAuthError),
        (403, BackendPermissionError),
        (404, BackendNotFoundError),
        (400, BackendValidationError),
        (500, BackendUnavailableError),
    ])
    def test_statuscode_wird_übersetzt(self, backend, http, status, erwartet):
        http.get(f'{API}/domains/', status_code=status, json={'detail': 'nope'})
        with pytest.raises(erwartet):
            backend.list_zones()

    def test_verbindungsfehler_wird_übersetzt(self, backend, http):
        http.get(f'{API}/domains/', exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(BackendUnavailableError):
            backend.list_zones()


class TestPaginierungsZiel:
    """Eine Antwort darf uns nicht mit dem Token zu einem fremden Host schicken."""

    def test_link_auf_fremden_host_wird_abgelehnt(self, backend, http):
        boese = 'https://angreifer.example/abgriff'
        http.get(f'{API}/domains/example.com/rrsets/',
                 json=[{'subname': 'a', 'type': 'A', 'ttl': 3600,
                        'records': ['192.0.2.1']}],
                 headers={'Link': f'<{boese}>; rel="next"'})

        with pytest.raises(BackendValidationError) as excinfo:
            backend.list_rrsets(ZONE)

        assert 'fremden Ursprung' in str(excinfo.value)
        assert boese not in [r.url for r in http.request_history[1:]]

    def test_kein_request_an_den_fremden_host(self, backend, http):
        """Das Token darf den fremden Host nie erreichen."""
        boese = 'https://angreifer.example/abgriff'
        http.get(f'{API}/domains/', json=[{'name': 'example.com', 'minimum_ttl': 3600}],
                 headers={'Link': f'<{boese}>; rel="next"'})

        with pytest.raises(BackendValidationError):
            backend.list_zones()

        assert all('angreifer.example' not in r.url for r in http.request_history)

    def test_gleicher_ursprung_wird_gefolgt(self, backend, http):
        seite2 = f'{API}/domains/?cursor=zwei'
        http.get(f'{API}/domains/', [
            {'json': [{'name': 'a.example', 'minimum_ttl': 3600}],
             'headers': {'Link': f'<{seite2}>; rel="next"'}},
            {'json': [{'name': 'b.example', 'minimum_ttl': 3600}]},
        ])

        assert sorted(backend.list_zones()) == ['a.example', 'b.example']

    def test_anderes_schema_wird_abgelehnt(self, backend, http):
        """http statt https auf demselben Host ist ebenfalls ein Ursprungswechsel."""
        http.get(f'{API}/domains/', json=[],
                 headers={'Link': '<http://desec.io/api/v1/domains/?cursor=x>; rel="next"'})

        with pytest.raises(BackendValidationError):
            backend.list_zones()

    def test_eigene_api_base_bleibt_erlaubt(self, http):
        """Eine selbst konfigurierte Basis-URL definiert den erlaubten Ursprung."""
        b = DesecBackend(token='t', api_base='https://dns.intern.example/api/v1')
        seite2 = 'https://dns.intern.example/api/v1/domains/?cursor=zwei'
        http.get('https://dns.intern.example/api/v1/domains/', [
            {'json': [{'name': 'a.example', 'minimum_ttl': 3600}],
             'headers': {'Link': f'<{seite2}>; rel="next"'}},
            {'json': []},
        ])

        assert list(b.list_zones()) == ['a.example']
        b.close()
