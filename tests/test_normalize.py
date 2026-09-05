"""Tests der Normalisierungsschicht.

Sie entscheidet, was Anzeige und Upload gemeinsam sehen: TTL-Grenzen, nicht
schreibbare RR-Typen und die Form der RDATA. Läuft sie an der falschen Stelle,
zeigt --dry-run-compare andere Daten als der Upload schreibt.
"""
import pytest

from dnsjinja.backends import Zone
from dnsjinja.backends.desec import DesecBackend
from dnsjinja.backends.hetzner import HetznerBackend

from tests.conftest import write_config
from tests.test_unit import make_dnsjinja, make_rrset


@pytest.fixture
def desec():
    backend = DesecBackend(token='t')
    yield backend
    backend.close()


@pytest.fixture
def hetzner_caps():
    """Hetzner-Capabilities ohne echten hcloud-Client."""
    return HetznerBackend.capabilities


ZONE = Zone(name='example.com', zone_id='example.com')


def desired(ttl=300, records=('192.0.2.1',), name='www', rdtype='A'):
    return {(name, rdtype): (ttl, list(records))}


class TestTTLGrenzen:

    def test_zu_kleine_ttl_wird_angehoben(self, desec):
        result, warnings = desec.normalize_desired(ZONE, desired(ttl=300))
        assert result[('www', 'A')].ttl == 3600
        assert any('angehoben' in w for w in warnings)

    def test_zu_große_ttl_wird_gekappt(self, desec):
        result, warnings = desec.normalize_desired(ZONE, desired(ttl=999999))
        assert result[('www', 'A')].ttl == 86400
        assert any('gekappt' in w for w in warnings)

    def test_zulässige_ttl_bleibt_unverändert(self, desec):
        result, warnings = desec.normalize_desired(ZONE, desired(ttl=7200))
        assert result[('www', 'A')].ttl == 7200
        assert warnings == []

    def test_zonen_mindest_ttl_gewinnt_wenn_höher(self, desec):
        zone = Zone(name='example.com', zone_id='example.com', min_ttl=7200)
        result, _ = desec.normalize_desired(zone, desired(ttl=300))
        assert result[('www', 'A')].ttl == 7200

    def test_hetzner_lässt_300_stehen(self):
        """Die heutige TTL-Konvention darf sich durch den Umbau nicht ändern."""
        backend = HetznerBackend.__new__(HetznerBackend)   # ohne hcloud-Client
        result, warnings = HetznerBackend.normalize_desired(backend, ZONE, desired(ttl=300))
        assert result[('www', 'A')].ttl == 300
        assert warnings == []


class TestSchreibgeschützteTypen:

    @pytest.mark.parametrize('rdtype', ['SOA', 'DNSKEY', 'DS', 'RRSIG', 'CDS'])
    def test_desec_filtert_verwaltete_typen_aus_dem_soll(self, desec, rdtype):
        result, warnings = desec.normalize_desired(
            ZONE, desired(name='@', rdtype=rdtype, records=('irgendwas',))
        )
        assert result == {}
        assert any(rdtype in w for w in warnings)

    def test_normale_typen_bleiben(self, desec):
        result, _ = desec.normalize_desired(ZONE, desired(rdtype='A'))
        assert ('www', 'A') in result


class TestRDATAKanonisierung:

    def test_ipv6_schreibweise_wird_vereinheitlicht(self, desec):
        result, _ = desec.normalize_desired(
            ZONE, desired(rdtype='AAAA', records=('2001:0DB8:0000:0000:0000:0000:0000:0001',))
        )
        assert result[('www', 'AAAA')].records == ('2001:db8::1',)

    def test_mx_whitespace_wird_vereinheitlicht(self, desec):
        result, _ = desec.normalize_desired(
            ZONE, desired(rdtype='MX', records=('10    mx.example.com.',))
        )
        assert result[('www', 'MX')].records == ('10 mx.example.com.',)

    def test_langer_txt_wert_wird_gechunkt(self, desec):
        lang = 'v=DKIM1; k=rsa; p=' + 'A' * 400
        result, _ = desec.normalize_desired(
            ZONE, desired(rdtype='TXT', records=(f'"{lang}"',))
        )
        (wert,) = result[('www', 'TXT')].records
        # Zerlegt in mehrere character-strings, Nutzlast unverändert.
        from dnsjinja.backends.base import _split_txt_strings
        segmente = _split_txt_strings(wert)
        assert len(segmente) == 2
        assert all(len(seg.encode('utf-8')) <= 255 for seg in segmente)
        assert ''.join(segmente) == lang

    def test_kurzer_txt_wert_bleibt_einteilig(self, desec):
        result, _ = desec.normalize_desired(
            ZONE, desired(rdtype='TXT', records=('"v=spf1 -all"',))
        )
        assert result[('www', 'TXT')].records == ('"v=spf1 -all"',)

    def test_normalisierung_ist_idempotent(self, desec):
        einmal, _ = desec.normalize_desired(
            ZONE, desired(rdtype='TXT', records=('"' + 'B' * 400 + '"',))
        )
        wert = einmal[('www', 'TXT')].records[0]
        zweimal, _ = desec.normalize_desired(
            ZONE, desired(rdtype='TXT', records=(wert,))
        )
        assert zweimal[('www', 'TXT')].records[0] == wert

    def test_apex_bleibt_at_zeichen(self, desec):
        result, _ = desec.normalize_desired(ZONE, desired(name='@', rdtype='A'))
        assert ('@', 'A') in result


class TestAnzeigeUndUploadStimmenÜberein:
    """Die Invariante, um die es bei der Normalisierungsstelle geht."""

    def test_plan_ist_nach_upload_idempotent(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, upload=True)
        dj.upload_zone('example.com')

        # Zweiter Planungslauf gegen den nun geschriebenen Zustand.
        plan = dj._plan_zone_rrsets('example.com')
        assert plan, 'der Plan darf nicht leer sein'
        assert {c.action for c in plan} == {'unchanged'}

    def test_anzeige_und_upload_sehen_dieselben_änderungen(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        fake_backend.rrsets['example.com'] = [make_rrset('alt', 'A', 300, ['192.0.2.1'])]

        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, upload=True)
        dj.dry_run_compare()
        angezeigt = capsys.readouterr().out
        assert fake_backend.applied == [], 'der Trockenlauf darf nichts schreiben'

        dj.upload_zone('example.com')
        geschrieben = {(c.action, c.name, c.rdtype) for c in fake_backend.applied[0]}

        assert ('create', '@', 'NS') in geschrieben
        assert ('delete', 'alt', 'A') in geschrieben
        assert '+ @/NS' in angezeigt and '- alt/A' in angezeigt
        assert len(geschrieben) == 2
