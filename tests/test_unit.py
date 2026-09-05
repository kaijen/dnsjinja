"""Unit-Tests für DNSJinja.

Alle Backend-Aufrufe und DNS-Abfragen sind gemockt.
Keine Netzwerkverbindung erforderlich.
"""
import pytest
from unittest.mock import MagicMock, call
from pathlib import Path

from dnsjinja.dnsjinja import DNSJinja, UploadError
from dnsjinja.backends import BackendError, BackendUnavailableError, RRSet
from tests.conftest import write_config


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, **kwargs):
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

    def test_bekannte_domain_wird_befüllt(self, data_dir, config_file, fake_backend, mock_dns_resolver):
        """Domains, die bei Hetzner vorhanden sind, werden korrekt in _zones eingetragen."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)

        assert list(dj._zones) == ['example.com']
        assert dj.config['domains']['example.com']['zone-id'] == 'test-zone-id-123'
        assert dj.config['domains']['example.com']['zone-file'] == 'example.com.zone'

    def test_fehlende_domain_wird_ignoriert(self, data_dir, fake_backend, mock_dns_resolver, capsys):
        """Domain in config aber nicht bei Hetzner → Warnung + aus config entfernt."""
        config_path = write_config(data_dir, ['nicht-vorhanden.de'])

        dj = make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver)

        assert list(dj.config['domains']) == []
        out = capsys.readouterr().out
        assert 'nicht-vorhanden.de' in out
        assert 'ignoriert' in out

    def test_create_missing_legt_zone_an(self, data_dir, fake_backend, mock_dns_resolver, capsys):
        """Mit --create-missing wird eine fehlende Domain bei Hetzner angelegt."""
        config_path = write_config(data_dir, ['neu-anlegen.de'])

        dj = make_dnsjinja(
            data_dir, config_path, fake_backend, mock_dns_resolver,
            create_missing=True,
        )

        assert fake_backend.created == ['neu-anlegen.de']
        assert list(dj._zones) == ['neu-anlegen.de']
        assert dj._zones['neu-anlegen.de'].name == 'neu-anlegen.de'
        assert 'angelegt' in capsys.readouterr().out

    def test_create_missing_api_fehler_wird_ignoriert(
        self, data_dir, fake_backend, mock_dns_resolver, capsys
    ):
        """Schlägt das Anlegen fehl, wird die Domain mit Meldung übersprungen."""
        config_path = write_config(data_dir, ['fehler.de'])
        fake_backend.fail_on['create_zone'] = BackendError('API-Fehler')

        dj = make_dnsjinja(
            data_dir, config_path, fake_backend, mock_dns_resolver,
            create_missing=True,
        )

        assert list(dj.config['domains']) == []
        out = capsys.readouterr().out
        assert 'nicht angelegt' in out

    def test_unbekannte_hetzner_domain_gibt_warnung(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Zones, die bei Hetzner aber nicht in der Config stehen, erzeugen eine Warnung."""
        fake_backend.add_zone('unbekannt.de')

        make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)

        out = capsys.readouterr().out
        assert 'unbekannt.de' in out
        assert 'prüfen' in out

    def test_mehrere_domains_gleichzeitig(self, data_dir, fake_backend, mock_dns_resolver):
        """Mehrere Domains werden alle korrekt befüllt."""
        fake_backend.zones.clear()
        fake_backend.add_zone('a.de')
        fake_backend.add_zone('b.de')

        config_path = write_config(data_dir, ['a.de', 'b.de'])
        dj = make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver)

        assert dj.config['domains']['a.de']['zone-id'] == 'id-a.de'
        assert dj.config['domains']['b.de']['zone-id'] == 'id-b.de'
        assert len(dj._zones) == 2


# ---------------------------------------------------------------------------
# upload_zone() / upload_zones()
# ---------------------------------------------------------------------------

class TestUploadZone:

    def test_upload_erfolgreich(self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys):
        """Erfolgreicher Upload gibt Bestätigungsmeldung aus."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, upload=True)

        dj.upload_zone('example.com')

        zone = dj._zones['example.com']
        assert fake_backend.calls.count(('list_rrsets', zone)) == 1
        # NS-RRSet wird erstellt (SOA wird übersprungen)
        assert len(fake_backend.applied) == 1
        (change,) = fake_backend.applied[0]
        assert (change.action, change.name, change.rdtype) == ('create', '@', 'NS')
        assert 'erfolgreich aktualisiert' in capsys.readouterr().out

    def test_upload_fehler_wirft_exception_und_schreibt_exitcode(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Bei Upload-Fehler wird UploadError geworfen und Exit-Code 254 geschrieben."""
        fake_backend.fail_on['list_rrsets'] = BackendUnavailableError('Verbindungsfehler')
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, upload=True)

        with pytest.raises(UploadError):
            dj.upload_zone('example.com')

        assert dj.exit_status_file.read_text(encoding='utf-8') == '254'

    def test_upload_zones_setzt_bei_fehler_fort(
        self, data_dir, fake_backend, mock_dns_resolver, capsys
    ):
        """upload_zones() bricht bei einer fehlerhaften Domain nicht ab."""
        fake_backend.zones.clear()
        fake_backend.add_zone('ok.de')
        fake_backend.add_zone('fail.de')
        fake_backend.fail_on_zone[('list_rrsets', 'fail.de')] = BackendUnavailableError('Fehler')

        config_path = write_config(data_dir, ['ok.de', 'fail.de'])
        dj = make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver, upload=True)

        dj.upload_zones()

        listed = [z.name for kind, z in fake_backend.calls if kind == 'list_rrsets']
        assert listed == ['ok.de', 'fail.de']
        assert 'erfolgreich aktualisiert' in capsys.readouterr().out

    def test_upload_zones_deaktiviert_tut_nichts(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """upload_zones() ohne --upload macht keine API-Aufrufe."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, upload=False)

        dj.upload_zones()

        assert not [c for c in fake_backend.calls if c[0] == 'list_rrsets']


# ---------------------------------------------------------------------------
# backup_zone() / backup_zones()
# ---------------------------------------------------------------------------

class TestBackupZone:

    def test_backup_schreibt_datei(self, data_dir, config_file, fake_backend, mock_dns_resolver):
        """Backup schreibt den Inhalt der Zone in eine Datei im backup-Verzeichnis."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, backup=True)

        dj.backup_zone('example.com')

        zone = dj._zones['example.com']
        assert fake_backend.calls.count(('export_zonefile', zone)) == 1
        backups = list((data_dir / 'zone-backups').iterdir())
        assert len(backups) == 1
        assert 'example.com.zone' in backups[0].name
        assert '$ORIGIN example.com.' in backups[0].read_text(encoding='utf-8')

    def test_backup_dateiname_enthält_serial(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Der Dateiname des Backups enthält den SOA-Zähler (2026020101)."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, backup=True)

        dj.backup_zone('example.com')

        backups = list((data_dir / 'zone-backups').iterdir())
        assert backups[0].name == 'example.com.zone.2026020101'

    def test_backup_api_fehler_gibt_meldung_aus(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Bei Backup-Fehler wird eine Fehlermeldung ausgegeben, keine Exception geworfen."""
        fake_backend.fail_on['export_zonefile'] = BackendUnavailableError('Netzwerkfehler')
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, backup=True)

        dj.backup_zone('example.com')  # darf nicht werfen

        assert 'nicht gesichert' in capsys.readouterr().out

    def test_backup_zones_deaktiviert_tut_nichts(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """backup_zones() ohne --backup macht keine API-Aufrufe."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, backup=False)

        dj.backup_zones()

        assert not [c for c in fake_backend.calls if c[0] == 'export_zonefile']


# ---------------------------------------------------------------------------
# write_zone_files()
# ---------------------------------------------------------------------------

class TestWriteZoneFiles:

    def test_write_erzeugt_datei(self, data_dir, config_file, fake_backend, mock_dns_resolver):
        """write_zone_files() schreibt das gerenderte Zone-File."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, write_zone=True)

        dj.write_zone_files()

        files = list((data_dir / 'zone-files').iterdir())
        assert len(files) == 1
        assert files[0].name.startswith('example.com.zone.')
        content = files[0].read_text(encoding='utf-8')
        assert '$ORIGIN example.com.' in content

    def test_write_deaktiviert_erzeugt_keine_datei(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """write_zone_files() ohne --write schreibt keine Dateien."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, write_zone=False)

        dj.write_zone_files()

        assert list((data_dir / 'zone-files').iterdir()) == []


# ---------------------------------------------------------------------------
# SOA-Seriennummer (_new_zone_serial)
# ---------------------------------------------------------------------------

class TestZoneSerial:

    def test_serial_selber_tag_wird_inkrementiert(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Am selben Tag wird der Zähler erhöht: 2026020101 → 2026020102."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj._today = '20260201'  # Gleicher Tag wie SOA-Präfix

        serial = dj._new_zone_serial('example.com')

        assert serial == '2026020102'

    def test_serial_neuer_tag_beginnt_bei_01(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """An einem neuen Tag beginnt der Zähler bei 01."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj._today = '20260215'  # Anderer Tag als SOA-Präfix (20260201)

        serial = dj._new_zone_serial('example.com')

        assert serial == '2026021501'

    def test_serial_format_yyyymmddnn(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Der Zähler hat immer das Format JJJJMMTTNN (10 Zeichen)."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj._today = '20260201'

        serial = dj._new_zone_serial('example.com')

        assert len(serial) == 10
        assert serial.isdigit()

    def test_serial_ueberlauf_bei_suffix_99_bricht_ab(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Bei Suffix 99 wird sys.exit(1) ausgelöst statt einer 11-stelligen Serial."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)

        # Mock überschreiben: aktueller Zähler endet auf 99
        soa_99 = MagicMock()
        soa_99.serial = 2026020199
        mock_dns_resolver.resolve.return_value = [soa_99]
        dj._dns_serials.clear()  # in __init__ gecachten Zähler verwerfen

        dj._today = '20260201'  # gleicher Tag wie Serial-Präfix → Inkrement wird versucht

        with pytest.raises(SystemExit) as exc_info:
            dj._new_zone_serial('example.com')
        assert exc_info.value.code == 1

    def test_serial_ohne_delegation_startet_bei_01(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Antwortet kein Nameserver (neue, noch nicht delegierte Domäne), wird JJJJMMTT01 benutzt."""
        import dns.resolver

        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj._today = '20260201'
        dj._dns_serials.clear()
        mock_dns_resolver.resolve.side_effect = dns.resolver.NoNameservers()

        serial = dj._new_zone_serial('example.com')

        assert serial == '2026020101'
        assert 'konnte nicht per DNS ermittelt werden' in capsys.readouterr().out

    def test_dns_serial_wird_nur_einmal_abgefragt(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Der per DNS ermittelte Zähler wird gecacht – keine zweite Abfrage pro Domäne."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        calls_after_init = mock_dns_resolver.resolve.call_count

        dj._get_zone_serial('example.com')

        assert mock_dns_resolver.resolve.call_count == calls_after_init

    def test_serial_wird_in_serials_gecacht(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """_create_zone_data() speichert den berechneten Serial in self._serials."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)

        assert list(dj._serials) == ['example.com']
        assert len(dj._serials['example.com']) == 10

    def test_write_zone_files_nutzt_gecachten_serial(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """write_zone_files() verwendet den gecachten Serial – kein zweiter DNS-Aufruf."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver, write_zone=True)
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
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
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
        self, data_dir, fake_backend, mock_dns_resolver, capsys
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
        self, data_dir, fake_backend, mock_dns_resolver
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
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """domain und soa_serial werden korrekt ins Zone-File gerendert."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        zone = dj.zones['example.com']
        assert '$ORIGIN example.com.' in zone
        assert dj._serials['example.com'] in zone


# ---------------------------------------------------------------------------
# _parse_zone_rrsets() – RDATA-Serialisierung (Bug #8)
# ---------------------------------------------------------------------------

class TestParseZoneRRSets:
    """Apex-CNAME-Ziele dürfen nicht zu '@' kollabieren (Hetzner lehnt das ab)."""

    APEX_CNAME_ZONE = (
        "$ORIGIN example.com.\n"
        "$TTL 3600\n"
        "@ IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. 2026020101 86400 10800 3600000 3600\n"
        "@ IN NS hydrogen.ns.hetzner.com.\n"
        "kai IN CNAME example.com.\n"
        "join IN CNAME verify\n"
        "www IN CNAME external.example.org.\n"
    )

    def _parse(self, data_dir, config_file, fake_backend, mock_dns_resolver):
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.zones['example.com'] = self.APEX_CNAME_ZONE
        return dj._parse_zone_rrsets('example.com')

    def test_apex_cname_ziel_wird_als_fqdn_ausgegeben(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """CNAME aufs Apex -> FQDN 'example.com.', NICHT '@'."""
        result = self._parse(data_dir, config_file, fake_backend, mock_dns_resolver)
        ttl, records = result[('kai', 'CNAME')]
        assert records == ['example.com.']

    def test_within_zone_ziel_wird_als_fqdn_ausgegeben(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Relatives Within-Zone-Ziel -> 'verify.example.com.', nicht 'verify'."""
        result = self._parse(data_dir, config_file, fake_backend, mock_dns_resolver)
        _, records = result[('join', 'CNAME')]
        assert records == ['verify.example.com.']

    def test_externes_ziel_bleibt_unveraendert(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Externe FQDN-Ziele bleiben identisch (keine Regression)."""
        result = self._parse(data_dir, config_file, fake_backend, mock_dns_resolver)
        _, records = result[('www', 'CNAME')]
        assert records == ['external.example.org.']

    def test_owner_namen_bleiben_relativ_inkl_apex(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Owner-Namen bleiben relativ; der Apex-Owner bleibt '@'."""
        result = self._parse(data_dir, config_file, fake_backend, mock_dns_resolver)
        owners = {name for (name, rdtype) in result}
        assert '@' in owners
        assert 'kai' in owners
        assert ('SOA' not in {rdtype for (_, rdtype) in result})


# ---------------------------------------------------------------------------
# _plan_zone_rrsets() / dry_run_compare()
# ---------------------------------------------------------------------------

def make_rrset(name, rtype, ttl, values, protected=False):
    """Baut ein RRSet in backendneutraler Form."""
    return RRSet(name=name, rdtype=rtype, ttl=ttl,
                 records=tuple(sorted(values)), protected=protected)


class TestPlanZoneRRSets:
    """Der Plan beschreibt die Differenz Live-Daten <-> Template."""

    NS = 'hydrogen.ns.hetzner.com.'

    def _plan(self, data_dir, config_file, fake_backend, mock_dns_resolver, current):
        fake_backend.rrsets['example.com'] = list(current)
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        return dj, {(c.name, c.rdtype): c for c in dj._plan_zone_rrsets('example.com')}

    def test_fehlendes_rrset_wird_als_create_geplant(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        _, plan = self._plan(data_dir, config_file, fake_backend, mock_dns_resolver, [])
        assert plan[('@', 'NS')].action == 'create'
        assert self.NS in plan[('@', 'NS')].records

    def test_identisches_rrset_wird_als_unchanged_geplant(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Template und Live-Daten gleich -> keine Änderung."""
        dj0 = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        ttl, values = dj0._parse_zone_rrsets('example.com')[('@', 'NS')]

        _, plan = self._plan(data_dir, config_file, fake_backend, mock_dns_resolver,
                             [make_rrset('@', 'NS', ttl, values)])
        assert plan[('@', 'NS')].action == 'unchanged'

    def test_abweichende_ttl_wird_als_update_geplant(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        dj0 = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        ttl, values = dj0._parse_zone_rrsets('example.com')[('@', 'NS')]

        _, plan = self._plan(data_dir, config_file, fake_backend, mock_dns_resolver,
                             [make_rrset('@', 'NS', ttl + 100, values)])
        change = plan[('@', 'NS')]
        assert change.action == 'update'
        assert change.current_ttl == ttl + 100 and change.ttl == ttl

    def test_ueberzaehliges_rrset_wird_als_delete_geplant(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        _, plan = self._plan(data_dir, config_file, fake_backend, mock_dns_resolver,
                             [make_rrset('alt', 'A', 300, ['192.0.2.1'])])
        change = plan[('alt', 'A')]
        assert change.action == 'delete'
        assert change.current_records == ['192.0.2.1']

    def test_geschuetztes_rrset_wird_als_protected_geplant(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        _, plan = self._plan(data_dir, config_file, fake_backend, mock_dns_resolver,
                             [make_rrset('alt', 'A', 300, ['192.0.2.1'], protected=True)])
        assert plan[('alt', 'A')].action == 'protected'

    def test_soa_wird_ignoriert(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """SOA wird von Hetzner verwaltet und taucht im Plan nicht auf."""
        _, plan = self._plan(data_dir, config_file, fake_backend, mock_dns_resolver,
                             [make_rrset('@', 'SOA', 3600, ['irgendwas'])])
        assert ('@', 'SOA') not in plan


class TestDryRunCompare:

    def test_zeigt_unterschiede_ohne_api_aenderungen(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Ausgabe listet Änderungen – aber es wird nichts geschrieben."""
        fake_backend.rrsets['example.com'] = [
            make_rrset('alt', 'A', 300, ['192.0.2.1'])
        ]
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)

        dj.dry_run_compare()

        out = capsys.readouterr().out
        assert 'example.com' in out
        assert '+ @/NS' in out
        assert '- alt/A' in out
        assert fake_backend.applied == []

    def test_meldet_keine_unterschiede(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        dj0 = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        ttl, values = dj0._parse_zone_rrsets('example.com')[('@', 'NS')]
        fake_backend.rrsets['example.com'] = [make_rrset('@', 'NS', ttl, values)]

        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.dry_run_compare()

        assert 'Keine Unterschiede' in capsys.readouterr().out

    def test_api_fehler_bricht_nicht_ab(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Eine unerreichbare Zone beendet den Vergleich nicht."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        fake_backend.fail_on['list_rrsets'] = BackendUnavailableError('Fehler')

        dj.dry_run_compare()

        assert 'konnten nicht gelesen werden' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Trockenlauf-Modi legen keine Zonen an
# ---------------------------------------------------------------------------

class TestDryRunLegtKeineZonenAn:
    """--create-missing darf im Trockenlauf niemals greifen."""

    @pytest.mark.parametrize('flag', ['--dry-run', '--dry-run-compare'])
    def test_create_missing_wird_im_trockenlauf_ignoriert(
        self, data_dir, fake_backend, mock_dns_resolver, flag
    ):
        from click.testing import CliRunner
        from dnsjinja.dnsjinja import run

        # Konfigurierte Domain existiert beim Backend nicht
        config_path = write_config(data_dir, ['neu.de'])
        fake_backend.zones.clear()

        result = CliRunner().invoke(run, [
            '-d', str(data_dir), '-c', str(config_path),
            '--auth-api-token', 'test-token', '-C', flag,
        ])

        assert result.exit_code == 0, result.output
        assert fake_backend.created == []
        assert 'im Trockenlauf ignoriert' in result.output


# ---------------------------------------------------------------------------
# TTL-Abweichungen in der Anzeige
# ---------------------------------------------------------------------------

class TestTTLAnzeige:
    """Reine TTL-Diffs werden ausgeblendet - der Upload gleicht sie aber an."""

    def _dj_mit_ttl_diff(self, data_dir, config_file, fake_backend, mock_dns_resolver):
        """Live-RRSet mit identischem RDATA, aber abweichender TTL."""
        dj0 = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        ttl, values = dj0._parse_zone_rrsets('example.com')[('@', 'NS')]
        fake_backend.rrsets['example.com'] = [
            make_rrset('@', 'NS', ttl + 3300, values)
        ]
        return make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)

    def test_reiner_ttl_diff_wird_ausgeblendet(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        dj = self._dj_mit_ttl_diff(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.dry_run_compare()

        out = capsys.readouterr().out
        assert '~ @/NS' not in out
        assert 'Keine Unterschiede' in out

    def test_ausgeblendeter_ttl_diff_wird_im_hinweis_genannt(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Die Anzeige darf nicht verschweigen, dass der Upload die TTL anfasst."""
        dj = self._dj_mit_ttl_diff(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.dry_run_compare()

        out = capsys.readouterr().out
        assert '1 RRSet(s) weichen nur in der TTL ab' in out
        assert '--show-ttl' in out

    def test_show_ttl_zeigt_den_diff(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        dj = self._dj_mit_ttl_diff(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.dry_run_compare(show_ttl=True)

        out = capsys.readouterr().out
        assert '~ @/NS' in out and '->' in out
        assert 'Hinweis:' not in out

    def test_rdata_diff_bleibt_sichtbar_ohne_ttl_pfeil(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, capsys
    ):
        """Weicht auch das RDATA ab, wird der Record gezeigt - ohne TTL-Pfeil."""
        fake_backend.rrsets['example.com'] = [
            make_rrset('@', 'NS', 3600, ['fremd.ns.example.'])
        ]
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.dry_run_compare()

        out = capsys.readouterr().out
        assert '~ @/NS  (TTL 3600)' in out
        assert '- fremd.ns.example.' in out
        assert '->' not in out

    def test_upload_gleicht_ttl_weiterhin_an(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Regressionsschutz: die Anzeige-Regel darf den Upload nicht verändern.

        Dass Hetzner daraus einen eigenen change_ttl-Aufruf macht, prüft
        test_backend_hetzner.py – hier zählt nur, dass die Änderung im Plan steht.
        """
        dj = self._dj_mit_ttl_diff(data_dir, config_file, fake_backend, mock_dns_resolver)
        dj.upload_zone('example.com')

        (change,) = fake_backend.applied[0]
        assert change.action == 'update'
        assert change.current_ttl != change.ttl


# ---------------------------------------------------------------------------
# Backend-Auswahl über config.json
# ---------------------------------------------------------------------------

class TestBackendAuswahl:
    """global.dns-backend steuert, welches Backend benutzt wird."""

    def _config_mit(self, data_dir, global_extra):
        import json as _json
        from tests.conftest import make_config
        cfg = make_config(['example.com'])
        cfg['global'].update(global_extra)
        path = data_dir / 'config' / 'config.json'
        path.write_text(_json.dumps(cfg), encoding='utf-8')
        return path

    def test_ohne_angabe_bleibt_hetzner_der_default(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        """Bestehende Konfigurationen ohne dns-backend ändern ihr Verhalten nicht."""
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        assert dj.backend_name == 'hetzner'

    def test_konfigurierter_name_wird_übernommen(
        self, data_dir, fake_backend, mock_dns_resolver
    ):
        config_path = self._config_mit(data_dir, {'dns-backend': 'desec'})
        dj = make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver)
        assert dj.backend_name == 'desec'

    def test_unbekanntes_backend_bricht_mit_namensliste_ab(
        self, data_dir, fake_backend, mock_dns_resolver, capsys
    ):
        config_path = self._config_mit(data_dir, {'dns-backend': 'gibtsnicht'})

        with pytest.raises(SystemExit) as excinfo:
            make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver)

        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert 'hetzner' in out and 'desec' in out

    def test_api_base_default_kommt_vom_backend(
        self, data_dir, config_file, fake_backend, mock_dns_resolver
    ):
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        assert dj._api_base == 'https://api.hetzner.cloud/v1'

    def test_desec_bringt_eigene_api_base_mit(
        self, data_dir, fake_backend, mock_dns_resolver
    ):
        config_path = self._config_mit(data_dir, {'dns-backend': 'desec'})
        dj = make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver)
        assert dj._api_base == 'https://desec.io/api/v1'

    def test_konfigurierte_api_base_gewinnt(
        self, data_dir, fake_backend, mock_dns_resolver
    ):
        config_path = self._config_mit(
            data_dir, {'dns-api-base': 'https://dns.example/v1/'}
        )
        dj = make_dnsjinja(data_dir, config_path, fake_backend, mock_dns_resolver)
        assert dj._api_base == 'https://dns.example/v1'

    def test_backendspezifisches_token_wird_gelesen(
        self, data_dir, fake_backend, mock_dns_resolver, monkeypatch
    ):
        monkeypatch.setenv('DNSJINJA_DESEC_AUTH_API_TOKEN', 'desec-token')
        monkeypatch.setenv('DNSJINJA_AUTH_API_TOKEN', 'allgemeines-token')
        config_path = self._config_mit(data_dir, {'dns-backend': 'desec'})

        dj = DNSJinja(datadir=str(data_dir), config_file=str(config_path),
                      auth_api_token='')

        assert dj.auth_api_token == 'desec-token'

    def test_allgemeines_token_als_rückfall(
        self, data_dir, fake_backend, mock_dns_resolver, monkeypatch
    ):
        monkeypatch.delenv('DNSJINJA_DESEC_AUTH_API_TOKEN', raising=False)
        monkeypatch.setenv('DNSJINJA_AUTH_API_TOKEN', 'allgemeines-token')
        config_path = self._config_mit(data_dir, {'dns-backend': 'desec'})

        dj = DNSJinja(datadir=str(data_dir), config_file=str(config_path),
                      auth_api_token='')

        assert dj.auth_api_token == 'allgemeines-token'

    def test_cli_option_schlägt_beide_umgebungsvariablen(
        self, data_dir, config_file, fake_backend, mock_dns_resolver, monkeypatch
    ):
        monkeypatch.setenv('DNSJINJA_AUTH_API_TOKEN', 'aus-der-umgebung')
        dj = make_dnsjinja(data_dir, config_file, fake_backend, mock_dns_resolver)
        assert dj.auth_api_token == 'test-token-unit'
