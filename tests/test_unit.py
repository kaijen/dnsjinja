"""Unit-Tests für DNSJinja.

Alle Hetzner-API-Aufrufe und DNS-Abfragen sind gemockt.
Keine Netzwerkverbindung erforderlich.
"""
import pytest
import hcloud
from unittest.mock import MagicMock, call
from pathlib import Path

from dnsjinja.dnsjinja import DNSJinja, UploadError
from tests.conftest import write_config


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, **kwargs):
    """Erstellt eine DNSJinja-Instanz mit gemockten Abhängigkeiten."""
    return DNSJinja(
        datadir=str(data_dir),
        config_file=str(config_file),
        auth_api_token='test-token-unit',
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _prepare_zones()
# ---------------------------------------------------------------------------

class TestPrepareZones:

    def test_bekannte_domain_wird_befüllt(self, data_dir, config_file, mock_client, mock_dns_resolver):
        """Domains, die bei Hetzner vorhanden sind, werden korrekt in _hetzner_zones eingetragen."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)

        assert 'example.com' in dj._hetzner_zones
        assert dj.config['domains']['example.com']['zone-id'] == 'test-zone-id-123'
        assert dj.config['domains']['example.com']['zone-file'] == 'example.com.zone'

    def test_fehlende_domain_wird_ignoriert(self, data_dir, mock_client, mock_dns_resolver, capsys):
        """Domain in config aber nicht bei Hetzner → Warnung + aus config entfernt."""
        config_path = write_config(data_dir, ['nicht-vorhanden.de'])

        dj = make_dnsjinja(data_dir, config_path, mock_client, mock_dns_resolver)

        assert 'nicht-vorhanden.de' not in dj.config['domains']
        out = capsys.readouterr().out
        assert 'nicht-vorhanden.de' in out
        assert 'ignoriert' in out

    def test_create_missing_legt_zone_an(self, data_dir, mock_client, mock_dns_resolver, capsys):
        """Mit --create-missing wird eine fehlende Domain bei Hetzner angelegt."""
        config_path = write_config(data_dir, ['neu-anlegen.de'])

        new_zone = MagicMock()
        new_zone.name = 'neu-anlegen.de'
        new_zone.id = 'new-zone-id-456'
        create_resp = MagicMock()
        create_resp.zone = new_zone
        mock_client.zones.create.return_value = create_resp

        dj = make_dnsjinja(
            data_dir, config_path, mock_client, mock_dns_resolver,
            create_missing=True,
        )

        mock_client.zones.create.assert_called_once_with(name='neu-anlegen.de', mode='primary')
        assert 'neu-anlegen.de' in dj._hetzner_zones
        assert dj._hetzner_zones['neu-anlegen.de'] is new_zone
        assert 'angelegt' in capsys.readouterr().out

    def test_create_missing_api_fehler_wird_ignoriert(
        self, data_dir, mock_client, mock_dns_resolver, capsys
    ):
        """Schlägt das Anlegen fehl, wird die Domain mit Meldung übersprungen."""
        config_path = write_config(data_dir, ['fehler.de'])
        mock_client.zones.create.side_effect = hcloud.APIException(
            code=422, message='API-Fehler', details={}
        )

        dj = make_dnsjinja(
            data_dir, config_path, mock_client, mock_dns_resolver,
            create_missing=True,
        )

        assert 'fehler.de' not in dj.config['domains']
        out = capsys.readouterr().out
        assert 'nicht angelegt' in out

    def test_unbekannte_hetzner_domain_gibt_warnung(
        self, data_dir, config_file, mock_client, mock_dns_resolver, capsys
    ):
        """Zones, die bei Hetzner aber nicht in der Config stehen, erzeugen eine Warnung."""
        extra_zone = MagicMock()
        extra_zone.name = 'unbekannt.de'
        extra_zone.id = 'extra-id'
        mock_client.zones.get_all.return_value = [
            mock_client.zones.get_all.return_value[0],  # example.com
            extra_zone,
        ]

        make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)

        out = capsys.readouterr().out
        assert 'unbekannt.de' in out
        assert 'prüfen' in out

    def test_mehrere_domains_gleichzeitig(self, data_dir, mock_client, mock_dns_resolver):
        """Mehrere Domains werden alle korrekt befüllt."""
        zone_a = MagicMock(); zone_a.name = 'a.de'; zone_a.id = 'id-a'
        zone_b = MagicMock(); zone_b.name = 'b.de'; zone_b.id = 'id-b'
        mock_client.zones.get_all.return_value = [zone_a, zone_b]

        config_path = write_config(data_dir, ['a.de', 'b.de'])
        dj = make_dnsjinja(data_dir, config_path, mock_client, mock_dns_resolver)

        assert dj.config['domains']['a.de']['zone-id'] == 'id-a'
        assert dj.config['domains']['b.de']['zone-id'] == 'id-b'
        assert len(dj._hetzner_zones) == 2


# ---------------------------------------------------------------------------
# upload_zone() / upload_zones()
# ---------------------------------------------------------------------------

class TestUploadZone:

    def test_upload_erfolgreich(self, data_dir, config_file, mock_client, mock_dns_resolver, capsys):
        """Erfolgreicher Upload gibt Bestätigungsmeldung aus."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, upload=True)

        dj.upload_zone('example.com')

        mock_client.zones.get_rrset_all.assert_called_once_with(
            dj._hetzner_zones['example.com'],
        )
        # NS-RRSet wird erstellt (SOA wird übersprungen)
        mock_client.zones.create_rrset.assert_called_once()
        create_kwargs = mock_client.zones.create_rrset.call_args
        assert create_kwargs.kwargs['name'] == '@'
        assert create_kwargs.kwargs['type'] == 'NS'
        assert 'erfolgreich aktualisiert' in capsys.readouterr().out

    def test_upload_fehler_wirft_exception_und_schreibt_exitcode(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """Bei Upload-Fehler wird UploadError geworfen und Exit-Code 254 geschrieben."""
        mock_client.zones.get_rrset_all.side_effect = hcloud.APIException(
            code=500, message='Verbindungsfehler', details={}
        )
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, upload=True)

        with pytest.raises(UploadError):
            dj.upload_zone('example.com')

        assert dj.exit_status_file.read_text(encoding='utf-8') == '254'

    def test_upload_zones_setzt_bei_fehler_fort(
        self, data_dir, mock_client, mock_dns_resolver, capsys
    ):
        """upload_zones() bricht bei einer fehlerhaften Domain nicht ab."""
        zone_a = MagicMock(); zone_a.name = 'ok.de'; zone_a.id = 'id-ok'
        zone_b = MagicMock(); zone_b.name = 'fail.de'; zone_b.id = 'id-fail'
        mock_client.zones.get_all.return_value = [zone_a, zone_b]

        call_count = 0

        def get_rrset_side_effect(zone, **kwargs):
            nonlocal call_count
            call_count += 1
            if zone.name == 'fail.de':
                raise hcloud.APIException(code=500, message='Fehler', details={})
            return []

        mock_client.zones.get_rrset_all.side_effect = get_rrset_side_effect
        config_path = write_config(data_dir, ['ok.de', 'fail.de'])
        dj = make_dnsjinja(data_dir, config_path, mock_client, mock_dns_resolver, upload=True)

        dj.upload_zones()

        assert call_count == 2
        assert 'erfolgreich aktualisiert' in capsys.readouterr().out

    def test_upload_zones_deaktiviert_tut_nichts(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """upload_zones() ohne --upload macht keine API-Aufrufe."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, upload=False)

        dj.upload_zones()

        mock_client.zones.get_rrset_all.assert_not_called()


# ---------------------------------------------------------------------------
# backup_zone() / backup_zones()
# ---------------------------------------------------------------------------

class TestBackupZone:

    def test_backup_schreibt_datei(self, data_dir, config_file, mock_client, mock_dns_resolver):
        """Backup schreibt den Inhalt der Zone in eine Datei im backup-Verzeichnis."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, backup=True)

        dj.backup_zone('example.com')

        mock_client.zones.export_zonefile.assert_called_once_with(
            dj._hetzner_zones['example.com']
        )
        backups = list((data_dir / 'zone-backups').iterdir())
        assert len(backups) == 1
        assert 'example.com.zone' in backups[0].name
        assert '$ORIGIN example.com.' in backups[0].read_text(encoding='utf-8')

    def test_backup_dateiname_enthält_serial(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """Der Dateiname des Backups enthält den SOA-Zähler (2026020101)."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, backup=True)

        dj.backup_zone('example.com')

        backups = list((data_dir / 'zone-backups').iterdir())
        assert backups[0].name == 'example.com.zone.2026020101'

    def test_backup_api_fehler_gibt_meldung_aus(
        self, data_dir, config_file, mock_client, mock_dns_resolver, capsys
    ):
        """Bei Backup-Fehler wird eine Fehlermeldung ausgegeben, keine Exception geworfen."""
        mock_client.zones.export_zonefile.side_effect = hcloud.APIException(
            code=500, message='Netzwerkfehler', details={}
        )
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, backup=True)

        dj.backup_zone('example.com')  # darf nicht werfen

        assert 'nicht gesichert' in capsys.readouterr().out

    def test_backup_zones_deaktiviert_tut_nichts(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """backup_zones() ohne --backup macht keine API-Aufrufe."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, backup=False)

        dj.backup_zones()

        mock_client.zones.export_zonefile.assert_not_called()


# ---------------------------------------------------------------------------
# write_zone_files()
# ---------------------------------------------------------------------------

class TestWriteZoneFiles:

    def test_write_erzeugt_datei(self, data_dir, config_file, mock_client, mock_dns_resolver):
        """write_zone_files() schreibt das gerenderte Zone-File."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, write_zone=True)

        dj.write_zone_files()

        files = list((data_dir / 'zone-files').iterdir())
        assert len(files) == 1
        assert files[0].name.startswith('example.com.zone.')
        content = files[0].read_text(encoding='utf-8')
        assert '$ORIGIN example.com.' in content

    def test_write_deaktiviert_erzeugt_keine_datei(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """write_zone_files() ohne --write schreibt keine Dateien."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, write_zone=False)

        dj.write_zone_files()

        assert list((data_dir / 'zone-files').iterdir()) == []


# ---------------------------------------------------------------------------
# SOA-Seriennummer (_new_zone_serial)
# ---------------------------------------------------------------------------

class TestZoneSerial:

    def test_serial_selber_tag_wird_inkrementiert(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """Am selben Tag wird der Zähler erhöht: 2026020101 → 2026020102."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)
        dj._today = '20260201'  # Gleicher Tag wie SOA-Präfix

        serial = dj._new_zone_serial('example.com')

        assert serial == '2026020102'

    def test_serial_neuer_tag_beginnt_bei_01(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """An einem neuen Tag beginnt der Zähler bei 01."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)
        dj._today = '20260215'  # Anderer Tag als SOA-Präfix (20260201)

        serial = dj._new_zone_serial('example.com')

        assert serial == '2026021501'

    def test_serial_format_yyyymmddnn(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """Der Zähler hat immer das Format JJJJMMTTNN (10 Zeichen)."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)
        dj._today = '20260201'

        serial = dj._new_zone_serial('example.com')

        assert len(serial) == 10
        assert serial.isdigit()

    def test_serial_ueberlauf_bei_suffix_99_bricht_ab(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """Bei Suffix 99 wird sys.exit(1) ausgelöst statt einer 11-stelligen Serial."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)

        # Mock überschreiben: aktueller Zähler endet auf 99
        soa_99 = MagicMock()
        soa_99.serial = 2026020199
        mock_dns_resolver.resolve.return_value = [soa_99]

        dj._today = '20260201'  # gleicher Tag wie Serial-Präfix → Inkrement wird versucht

        with pytest.raises(SystemExit) as exc_info:
            dj._new_zone_serial('example.com')
        assert exc_info.value.code == 1

    def test_serial_wird_in_serials_gecacht(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """_create_zone_data() speichert den berechneten Serial in self._serials."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)

        assert 'example.com' in dj._serials
        assert len(dj._serials['example.com']) == 10

    def test_write_zone_files_nutzt_gecachten_serial(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """write_zone_files() verwendet den gecachten Serial – kein zweiter DNS-Aufruf."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver, write_zone=True)
        dns_calls_after_init = mock_dns_resolver.resolve.call_count

        dj.write_zone_files()

        # Kein weiterer DNS-Aufruf durch write_zone_files()
        assert mock_dns_resolver.resolve.call_count == dns_calls_after_init

        # Dateiname enthält denselben Serial wie der Dateiinhalt
        files = list((data_dir / 'zone-files').iterdir())
        serial_in_name = files[0].name.split('.')[-1]
        assert serial_in_name == dj._serials['example.com']


# ---------------------------------------------------------------------------
# Token-Prüfung & Pfad-Validierung
# ---------------------------------------------------------------------------

class TestTokenUndPfad:

    def test_kein_token_bricht_mit_exit_1_ab(
        self, data_dir, config_file, mock_client, mock_dns_resolver, capsys
    ):
        """Ohne API-Token bricht __init__ frühzeitig mit sys.exit(1) ab."""
        with pytest.raises(SystemExit) as exc_info:
            DNSJinja(
                datadir=str(data_dir),
                config_file=str(config_file),
                auth_api_token='',
            )
        assert exc_info.value.code == 1
        assert 'API-Token' in capsys.readouterr().out

    def test_config_datei_statt_verzeichnis_bricht_ab(
        self, data_dir, mock_client, mock_dns_resolver, capsys
    ):
        """Wenn config_file ein Verzeichnis ist (nicht eine Datei), endet init mit exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            DNSJinja(
                datadir=str(data_dir),
                config_file=str(data_dir / 'config'),  # Verzeichnis statt Datei
                auth_api_token='test-token',
            )
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Schema-Validierung (3.3)
# ---------------------------------------------------------------------------

class TestConfigValidierung:

    def test_config_ohne_template_schlaegt_fehl(
        self, data_dir, mock_client, mock_dns_resolver
    ):
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
            "domains": {"test.com": {}},   # kein 'template'
        }), encoding='utf-8')
        with pytest.raises(SystemExit) as exc_info:
            DNSJinja(datadir=str(data_dir), config_file=str(config_path),
                     auth_api_token='test-token')
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Template-Rendering (3.4)
# ---------------------------------------------------------------------------

class TestZoneRendering:

    def test_template_variablen_werden_substituiert(
        self, data_dir, config_file, mock_client, mock_dns_resolver
    ):
        """domain und soa_serial werden korrekt ins Zone-File gerendert."""
        dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)
        zone = dj.zones['example.com']
        assert '$ORIGIN example.com.' in zone
        assert dj._serials['example.com'] in zone
