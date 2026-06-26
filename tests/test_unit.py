"""Unit-Tests für DNSJinja.

Der DNS-Provider ist ein In-Memory-`FakeProvider` (siehe conftest); es werden
keine echten API-Aufrufe gemacht und kein hcloud benötigt. DNS-Abfragen sind
gemockt. Keine Netzwerkverbindung erforderlich.
"""
import pytest
from pathlib import Path

from dnsjinja.dnsjinja import DNSJinja, UploadError
from dnsjinja.providers.base import ProviderError
from tests.conftest import FakeProvider, write_config


# ---------------------------------------------------------------------------
# _prepare_zones()
# ---------------------------------------------------------------------------

class TestPrepareZones:

    def test_bekannte_domain_wird_befüllt(self, make_dj, config_file):
        """Beim Provider vorhandene Domains landen in _zones / _provider_for."""
        provider = FakeProvider(zones=['example.com'])
        dj = make_dj(config_file, provider=provider)

        assert 'example.com' in dj._zones
        assert 'example.com' in dj._provider_for
        assert dj.config['domains']['example.com']['zone-id'] == 'id-example.com'
        assert dj.config['domains']['example.com']['zone-file'] == 'example.com.zone'

    def test_fehlende_domain_wird_ignoriert(self, make_dj, data_dir, capsys):
        """Domain in config aber nicht beim Provider → Warnung + aus config entfernt."""
        config_path = write_config(data_dir, ['nicht-vorhanden.de'])
        provider = FakeProvider(zones=[])  # keine Zonen

        dj = make_dj(config_path, provider=provider)

        assert 'nicht-vorhanden.de' not in dj.config['domains']
        out = capsys.readouterr().out
        assert 'nicht-vorhanden.de' in out
        assert 'ignoriert' in out

    def test_create_missing_legt_zone_an(self, make_dj, data_dir, capsys):
        """Mit --create-missing wird eine fehlende Domain beim Provider angelegt."""
        config_path = write_config(data_dir, ['neu-anlegen.de'])
        provider = FakeProvider(zones=[])

        dj = make_dj(config_path, provider=provider, create_missing=True)

        assert provider.calls_of('create_zone') == [('create_zone', 'neu-anlegen.de')]
        assert 'neu-anlegen.de' in dj._zones
        assert 'angelegt' in capsys.readouterr().out

    def test_create_missing_api_fehler_wird_ignoriert(self, make_dj, data_dir, capsys):
        """Schlägt das Anlegen fehl, wird die Domain mit Meldung übersprungen."""
        config_path = write_config(data_dir, ['fehler.de'])
        provider = FakeProvider(zones=[], fail={'create_zone': ProviderError('API-Fehler')})

        dj = make_dj(config_path, provider=provider, create_missing=True)

        assert 'fehler.de' not in dj.config['domains']
        assert 'nicht angelegt' in capsys.readouterr().out

    def test_unbekannte_provider_domain_gibt_warnung(self, make_dj, config_file, capsys):
        """Zonen beim Provider, die nicht in der Config stehen, erzeugen eine Warnung."""
        provider = FakeProvider(zones=['example.com', 'unbekannt.de'])

        make_dj(config_file, provider=provider)

        out = capsys.readouterr().out
        assert 'unbekannt.de' in out
        assert 'prüfen' in out

    def test_mehrere_domains_gleichzeitig(self, make_dj, data_dir):
        """Mehrere Domains werden alle korrekt befüllt."""
        config_path = write_config(data_dir, ['a.de', 'b.de'])
        provider = FakeProvider(zones=['a.de', 'b.de'])

        dj = make_dj(config_path, provider=provider)

        assert dj.config['domains']['a.de']['zone-id'] == 'id-a.de'
        assert dj.config['domains']['b.de']['zone-id'] == 'id-b.de'
        assert len(dj._zones) == 2


# ---------------------------------------------------------------------------
# upload_zone() / upload_zones()
# ---------------------------------------------------------------------------

class TestUploadZone:

    def test_upload_erfolgreich(self, make_dj, config_file, capsys):
        """Erfolgreicher Upload legt das NS-RRSet an (SOA wird übersprungen)."""
        provider = FakeProvider(zones=['example.com'])
        dj = make_dj(config_file, provider=provider, upload=True)

        dj.upload_zone('example.com')

        assert provider.calls_of('get_rrsets') == [('get_rrsets', 'example.com')]
        creates = provider.calls_of('create_rrset')
        assert len(creates) == 1
        # ('create_rrset', zone, name, type, ttl, records)
        assert creates[0][2] == '@'
        assert creates[0][3] == 'NS'
        assert 'erfolgreich aktualisiert' in capsys.readouterr().out

    def test_upload_fehler_wirft_exception_und_schreibt_exitcode(self, make_dj, config_file):
        """Bei Provider-Fehler wird UploadError geworfen und Exit-Code 254 geschrieben."""
        provider = FakeProvider(zones=['example.com'],
                                fail={'get_rrsets': ProviderError('Verbindungsfehler')})
        dj = make_dj(config_file, provider=provider, upload=True)

        with pytest.raises(UploadError):
            dj.upload_zone('example.com')

        assert dj.exit_status_file.read_text(encoding='utf-8') == '254'

    def test_upload_zones_setzt_bei_fehler_fort(self, make_dj, data_dir, capsys):
        """upload_zones() bricht bei einer fehlerhaften Domain nicht ab."""
        config_path = write_config(data_dir, ['ok.de', 'fail.de'])
        provider = FakeProvider(zones=['ok.de', 'fail.de'], fail_zones=['fail.de'])
        dj = make_dj(config_path, provider=provider, upload=True)

        dj.upload_zones()

        # Trotz Fehler bei fail.de wird ok.de erfolgreich verarbeitet (kein Abbruch).
        out = capsys.readouterr().out
        assert 'ok.de wurde bei fake erfolgreich aktualisiert' in out
        assert 'fail.de konnte nicht aktualisiert werden' in out

    def test_upload_zones_deaktiviert_tut_nichts(self, make_dj, config_file):
        """upload_zones() ohne --upload macht keine Provider-Aufrufe."""
        provider = FakeProvider(zones=['example.com'])
        dj = make_dj(config_file, provider=provider, upload=False)

        dj.upload_zones()

        assert provider.calls_of('get_rrsets') == []


# ---------------------------------------------------------------------------
# backup_zone() / backup_zones()
# ---------------------------------------------------------------------------

class TestBackupZone:

    def test_backup_schreibt_datei(self, make_dj, config_file, data_dir):
        """Backup schreibt den Zonefile-Export in eine Datei im backup-Verzeichnis."""
        provider = FakeProvider(zones=['example.com'],
                                export_text='$ORIGIN example.com.\n$TTL 3600\n')
        dj = make_dj(config_file, provider=provider, backup=True)

        dj.backup_zone('example.com')

        assert provider.calls_of('export_zonefile') == [('export_zonefile', 'example.com')]
        backups = list((data_dir / 'zone-backups').iterdir())
        assert len(backups) == 1
        assert 'example.com.zone' in backups[0].name
        assert '$ORIGIN example.com.' in backups[0].read_text(encoding='utf-8')

    def test_backup_dateiname_enthält_serial(self, make_dj, config_file, data_dir):
        """Der Dateiname des Backups enthält den SOA-Zähler (2026020101)."""
        provider = FakeProvider(zones=['example.com'])
        dj = make_dj(config_file, provider=provider, backup=True)

        dj.backup_zone('example.com')

        backups = list((data_dir / 'zone-backups').iterdir())
        assert backups[0].name == 'example.com.zone.2026020101'

    def test_backup_api_fehler_gibt_meldung_aus(self, make_dj, config_file, capsys):
        """Bei Backup-Fehler wird eine Fehlermeldung ausgegeben, keine Exception."""
        provider = FakeProvider(zones=['example.com'],
                                fail={'export_zonefile': ProviderError('Netzwerkfehler')})
        dj = make_dj(config_file, provider=provider, backup=True)

        dj.backup_zone('example.com')  # darf nicht werfen

        assert 'nicht gesichert' in capsys.readouterr().out

    def test_backup_ohne_export_support_wird_uebersprungen(self, make_dj, config_file, capsys, data_dir):
        """Provider ohne Zonefile-Export überspringt das Backup sauber (kein Crash)."""
        provider = FakeProvider(zones=['example.com'], supports_export=False)
        dj = make_dj(config_file, provider=provider, backup=True)

        dj.backup_zone('example.com')

        assert provider.calls_of('export_zonefile') == []
        assert 'übersprungen' in capsys.readouterr().out
        assert list((data_dir / 'zone-backups').iterdir()) == []

    def test_backup_zones_deaktiviert_tut_nichts(self, make_dj, config_file):
        """backup_zones() ohne --backup macht keine Provider-Aufrufe."""
        provider = FakeProvider(zones=['example.com'])
        dj = make_dj(config_file, provider=provider, backup=False)

        dj.backup_zones()

        assert provider.calls_of('export_zonefile') == []


# ---------------------------------------------------------------------------
# write_zone_files()
# ---------------------------------------------------------------------------

class TestWriteZoneFiles:

    def test_write_erzeugt_datei(self, make_dj, config_file, data_dir):
        """write_zone_files() schreibt das gerenderte Zone-File."""
        dj = make_dj(config_file, write_zone=True)

        dj.write_zone_files()

        files = list((data_dir / 'zone-files').iterdir())
        assert len(files) == 1
        assert files[0].name.startswith('example.com.zone.')
        content = files[0].read_text(encoding='utf-8')
        assert '$ORIGIN example.com.' in content

    def test_write_deaktiviert_erzeugt_keine_datei(self, make_dj, config_file, data_dir):
        """write_zone_files() ohne --write schreibt keine Dateien."""
        dj = make_dj(config_file, write_zone=False)

        dj.write_zone_files()

        assert list((data_dir / 'zone-files').iterdir()) == []


# ---------------------------------------------------------------------------
# SOA-Seriennummer (_new_zone_serial)
# ---------------------------------------------------------------------------

class TestZoneSerial:

    def test_serial_selber_tag_wird_inkrementiert(self, make_dj, config_file):
        """Am selben Tag wird der Zähler erhöht: 2026020101 → 2026020102."""
        dj = make_dj(config_file)
        dj._today = '20260201'

        assert dj._new_zone_serial('example.com') == '2026020102'

    def test_serial_neuer_tag_beginnt_bei_01(self, make_dj, config_file):
        """An einem neuen Tag beginnt der Zähler bei 01."""
        dj = make_dj(config_file)
        dj._today = '20260215'

        assert dj._new_zone_serial('example.com') == '2026021501'

    def test_serial_format_yyyymmddnn(self, make_dj, config_file):
        """Der Zähler hat immer das Format JJJJMMTTNN (10 Zeichen)."""
        dj = make_dj(config_file)
        dj._today = '20260201'

        serial = dj._new_zone_serial('example.com')
        assert len(serial) == 10
        assert serial.isdigit()

    def test_serial_ueberlauf_bei_suffix_99_bricht_ab(self, make_dj, config_file, mock_dns_resolver):
        """Bei Suffix 99 wird sys.exit(1) ausgelöst statt einer 11-stelligen Serial."""
        dj = make_dj(config_file)

        from unittest.mock import MagicMock
        soa_99 = MagicMock()
        soa_99.serial = 2026020199
        mock_dns_resolver.resolve.return_value = [soa_99]
        dj._today = '20260201'

        with pytest.raises(SystemExit) as exc_info:
            dj._new_zone_serial('example.com')
        assert exc_info.value.code == 1

    def test_serial_wird_in_serials_gecacht(self, make_dj, config_file):
        """_create_zone_data() speichert den berechneten Serial in self._serials."""
        dj = make_dj(config_file)

        assert 'example.com' in dj._serials
        assert len(dj._serials['example.com']) == 10

    def test_write_zone_files_nutzt_gecachten_serial(self, make_dj, config_file, mock_dns_resolver, data_dir):
        """write_zone_files() verwendet den gecachten Serial – kein zweiter DNS-Aufruf."""
        dj = make_dj(config_file, write_zone=True)
        dns_calls_after_init = mock_dns_resolver.resolve.call_count

        dj.write_zone_files()

        assert mock_dns_resolver.resolve.call_count == dns_calls_after_init
        files = list((data_dir / 'zone-files').iterdir())
        serial_in_name = files[0].name.split('.')[-1]
        assert serial_in_name == dj._serials['example.com']


# ---------------------------------------------------------------------------
# Token-Prüfung & Pfad-Validierung
# ---------------------------------------------------------------------------

class TestTokenUndPfad:

    def test_kein_token_bricht_mit_exit_1_ab(self, data_dir, config_file, mock_dns_resolver, capsys):
        """Ohne API-Token (Single-Provider) bricht __init__ mit sys.exit(1) ab."""
        with pytest.raises(SystemExit) as exc_info:
            DNSJinja(
                datadir=str(data_dir),
                config_file=str(config_file),
                auth_api_token='',
            )
        assert exc_info.value.code == 1
        assert 'API-Token' in capsys.readouterr().out

    def test_config_datei_statt_verzeichnis_bricht_ab(self, data_dir, mock_dns_resolver):
        """Wenn config_file ein Verzeichnis ist (nicht eine Datei), endet init mit exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            DNSJinja(
                datadir=str(data_dir),
                config_file=str(data_dir / 'config'),
                auth_api_token='test-token',
            )
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Schema-Validierung
# ---------------------------------------------------------------------------

class TestConfigValidierung:

    def test_config_ohne_template_schlaegt_fehl(self, data_dir, mock_dns_resolver):
        """Config ohne Pflichtfeld 'template' wird vom Schema abgewiesen."""
        import json
        config_path = data_dir / 'config' / 'config.json'
        config_path.write_text(json.dumps({
            "global": {
                "zone-files": "zone-files",
                "zone-backups": "zone-backups",
                "templates": "templates",
                "name-servers": ["213.133.100.98"],
            },
            "domains": {"test.com": {}},
        }), encoding='utf-8')
        with pytest.raises(SystemExit) as exc_info:
            DNSJinja(datadir=str(data_dir), config_file=str(config_path),
                     auth_api_token='test-token')
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Template-Rendering
# ---------------------------------------------------------------------------

class TestZoneRendering:

    def test_template_variablen_werden_substituiert(self, make_dj, config_file):
        """domain und soa_serial werden korrekt ins Zone-File gerendert."""
        dj = make_dj(config_file)
        zone = dj.zones['example.com']
        assert '$ORIGIN example.com.' in zone
        assert dj._serials['example.com'] in zone


# ---------------------------------------------------------------------------
# _parse_zone_rrsets() – RDATA-Serialisierung (Bug #8)
# ---------------------------------------------------------------------------

class TestParseZoneRRSets:
    """Apex-CNAME-Ziele dürfen nicht zu '@' kollabieren."""

    APEX_CNAME_ZONE = (
        "$ORIGIN example.com.\n"
        "$TTL 3600\n"
        "@ IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. 2026020101 86400 10800 3600000 3600\n"
        "@ IN NS hydrogen.ns.hetzner.com.\n"
        "kai IN CNAME example.com.\n"
        "join IN CNAME verify\n"
        "www IN CNAME external.example.org.\n"
    )

    def _parse(self, make_dj, config_file):
        dj = make_dj(config_file)
        dj.zones['example.com'] = self.APEX_CNAME_ZONE
        return dj._parse_zone_rrsets('example.com')

    def test_apex_cname_ziel_wird_als_fqdn_ausgegeben(self, make_dj, config_file):
        result = self._parse(make_dj, config_file)
        ttl, records = result[('kai', 'CNAME')]
        assert records == ['example.com.']

    def test_within_zone_ziel_wird_als_fqdn_ausgegeben(self, make_dj, config_file):
        result = self._parse(make_dj, config_file)
        _, records = result[('join', 'CNAME')]
        assert records == ['verify.example.com.']

    def test_externes_ziel_bleibt_unveraendert(self, make_dj, config_file):
        result = self._parse(make_dj, config_file)
        _, records = result[('www', 'CNAME')]
        assert records == ['external.example.org.']

    def test_owner_namen_bleiben_relativ_inkl_apex(self, make_dj, config_file):
        result = self._parse(make_dj, config_file)
        owners = {name for (name, rdtype) in result}
        assert '@' in owners
        assert 'kai' in owners
        assert ('SOA' not in {rdtype for (_, rdtype) in result})
