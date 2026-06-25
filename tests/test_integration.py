"""Integrationstests für DNSJinja.

Diese Tests verwenden die echte Hetzner Cloud API. Benötigte Umgebungsvariablen:

  DNSJINJA_AUTH_API_TOKEN  – Bearer-Token aus der Hetzner Cloud Console
  DNSJINJA_TEST_DOMAIN     – Testdomain, die bereits als primäre Zone bei
                             Hetzner eingerichtet ist

Hinweis: Der Upload-Test ersetzt alle DNS-Records der Testdomain durch ein
minimales Zone-File. Die Domain sollte deshalb ausschließlich für Tests
verwendet werden.

Die Tests werden automatisch übersprungen, wenn die Umgebungsvariablen nicht
gesetzt sind. Sie können auch gezielt ausgeführt werden:

  pytest tests/test_integration.py -m integration -v
"""
import pytest
from pathlib import Path

from dnsjinja.dnsjinja import DNSJinja
from tests.conftest import write_config

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def make_dnsjinja(data_dir, config_path, token, **kwargs):
    return DNSJinja(
        datadir=str(data_dir),
        config_file=str(config_path),
        auth_api_token=token,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def integration_config(data_dir, require_api_token, require_test_domain):
    """Config mit der echten Testdomain."""
    return write_config(data_dir, [require_test_domain])


@pytest.fixture
def dj(data_dir, integration_config, require_api_token):
    """DNSJinja-Instanz mit echter API-Verbindung."""
    return make_dnsjinja(data_dir, integration_config, require_api_token)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestZoneSync:

    def test_testdomain_ist_bei_hetzner_vorhanden(self, dj, require_test_domain):
        """Die Testdomain muss in _hetzner_zones eingetragen sein."""
        assert require_test_domain in dj._hetzner_zones
        assert require_test_domain in dj.config['domains']

    def test_zone_id_ist_befüllt(self, dj, require_test_domain):
        """zone-id wird aus der Hetzner API befüllt."""
        zone_id = dj.config['domains'][require_test_domain]['zone-id']
        assert zone_id
        assert isinstance(zone_id, (str, int))

    def test_zone_file_name_ist_gesetzt(self, dj, require_test_domain):
        """zone-file wird auf '<domain>.zone' gesetzt."""
        assert dj.config['domains'][require_test_domain]['zone-file'] == f'{require_test_domain}.zone'


class TestBackup:

    def test_backup_schreibt_datei(self, data_dir, integration_config, require_api_token, require_test_domain):
        """Backup einer echten Zone schreibt eine nicht-leere Datei."""
        dj = make_dnsjinja(data_dir, integration_config, require_api_token, backup=True)

        dj.backup_zone(require_test_domain)

        backups = list((data_dir / 'zone-backups').iterdir())
        assert len(backups) == 1, "Genau eine Backup-Datei erwartet"
        content = backups[0].read_text(encoding='utf-8')
        assert content.strip(), "Backup-Datei darf nicht leer sein"
        assert f'$ORIGIN {require_test_domain}' in content or require_test_domain in content

    def test_backup_dateiname_enthält_domain(self, data_dir, integration_config, require_api_token, require_test_domain):
        """Der Dateiname des Backups enthält den Domain-Namen."""
        dj = make_dnsjinja(data_dir, integration_config, require_api_token, backup=True)

        dj.backup_zone(require_test_domain)

        backups = list((data_dir / 'zone-backups').iterdir())
        assert require_test_domain in backups[0].name


class TestWrite:

    def test_write_erzeugt_zone_datei(self, data_dir, integration_config, require_api_token, require_test_domain):
        """write_zone_files() erzeugt eine lokale Zone-Datei mit dem Domain-Namen."""
        dj = make_dnsjinja(data_dir, integration_config, require_api_token, write_zone=True)

        dj.write_zone_files()

        files = list((data_dir / 'zone-files').iterdir())
        assert len(files) == 1
        assert require_test_domain in files[0].name
        content = files[0].read_text(encoding='utf-8')
        assert require_test_domain in content


class TestUpload:

    def test_upload_erfolgreich(self, data_dir, integration_config, require_api_token, require_test_domain):
        """Zone-File wird erfolgreich zu Hetzner hochgeladen (kein Fehler).

        HINWEIS: Dieser Test überschreibt alle DNS-Records der Testdomain
        mit dem minimalen Test-Template.
        """
        dj = make_dnsjinja(data_dir, integration_config, require_api_token, upload=True)

        dj.upload_zone(require_test_domain)  # darf keine Exception werfen


class TestUploadLebenszyklus:
    """Vollständiger Lebenszyklus: rudimentär → erweitert → reduziert → rudimentär.

    HINWEIS: Dieser Test überschreibt alle DNS-Records der Testdomain
    mehrfach. Die Domain sollte ausschließlich für Tests verwendet werden.
    Am Ende wird die Zone auf den minimalen Datensatz zurückgesetzt.
    """

    MINIMAL = """\
$ORIGIN {{ domain }}.
$TTL 3600
@ IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. {{ soa_serial }} 86400 10800 3600000 3600
@ IN NS hydrogen.ns.hetzner.com.
@ IN NS oxygen.ns.hetzner.com.
@ IN NS helium.ns.hetzner.de.
"""

    ERWEITERT = """\
$ORIGIN {{ domain }}.
$TTL 3600
@ IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. {{ soa_serial }} 86400 10800 3600000 3600
@ IN NS hydrogen.ns.hetzner.com.
@ IN NS oxygen.ns.hetzner.com.
@ IN NS helium.ns.hetzner.de.
@ IN A 192.0.2.1
@ IN MX 10 mail.{{ domain }}.
@ IN MX 20 mxext3.mailbox.org.
@ IN TXT "v=spf1 -all"
mail IN A 192.0.2.2
www IN A 192.0.2.1
"""

    REDUZIERT = """\
$ORIGIN {{ domain }}.
$TTL 3600
@ IN SOA hydrogen.ns.hetzner.com. dns.hetzner.com. {{ soa_serial }} 86400 10800 3600000 3600
@ IN NS hydrogen.ns.hetzner.com.
@ IN NS oxygen.ns.hetzner.com.
@ IN NS helium.ns.hetzner.de.
@ IN A 192.0.2.99
@ IN TXT "v=spf1 include:_spf.example.com -all"
"""

    @staticmethod
    def _get_rrset_map(dj, domain):
        """Liefert {(name, type): [value, ...]} der aktuellen Zone bei Hetzner."""
        zone = dj._hetzner_zones[domain]
        rrsets = dj.client.zones.get_rrset_all(zone)
        return {
            (r.name, r.type): sorted(rec.value for rec in (r.records or []))
            for r in rrsets
            if r.type != 'SOA'
        }

    @staticmethod
    def _upload_with_template(data_dir, template_content, domain, token):
        """Schreibt ein Template, erstellt eine DNSJinja-Instanz und lädt hoch."""
        (data_dir / 'templates' / 'test.tpl').write_text(template_content, encoding='utf-8')
        config_path = write_config(data_dir, [domain])
        dj = make_dnsjinja(data_dir, config_path, token, upload=True)
        dj.upload_zone(domain)
        return dj

    def test_lebenszyklus_records(
        self, data_dir, require_api_token, require_test_domain,
    ):
        """Testet Anlegen, Ändern und Löschen von A-, MX- und TXT-Records."""
        domain = require_test_domain

        # --- Schritt 1: Minimaler Datensatz (nur NS) --------------------------
        dj = self._upload_with_template(
            data_dir, self.MINIMAL, domain, require_api_token,
        )
        rrsets = self._get_rrset_map(dj, domain)
        assert ('@', 'NS') in rrsets
        assert ('@', 'A') not in rrsets
        assert ('@', 'MX') not in rrsets
        assert ('@', 'TXT') not in rrsets

        # --- Schritt 2: Records ergänzen (A, MX, TXT + Subdomains) ------------
        dj = self._upload_with_template(
            data_dir, self.ERWEITERT, domain, require_api_token,
        )
        rrsets = self._get_rrset_map(dj, domain)
        assert rrsets[('@', 'A')] == ['192.0.2.1']
        assert rrsets[('@', 'MX')] == ['10 mail', '20 mxext3.mailbox.org.']
        assert rrsets[('@', 'TXT')] == ['"v=spf1 -all"']
        assert rrsets[('mail', 'A')] == ['192.0.2.2']
        assert rrsets[('www', 'A')] == ['192.0.2.1']

        # --- Schritt 3: Records reduzieren (MX, www, mail entfernt; A+TXT geändert)
        dj = self._upload_with_template(
            data_dir, self.REDUZIERT, domain, require_api_token,
        )
        rrsets = self._get_rrset_map(dj, domain)
        assert rrsets[('@', 'A')] == ['192.0.2.99'], "A-Record muss aktualisiert sein"
        assert rrsets[('@', 'TXT')] == ['"v=spf1 include:_spf.example.com -all"']
        assert ('@', 'MX') not in rrsets, "MX muss gelöscht sein"
        assert ('www', 'A') not in rrsets, "www muss gelöscht sein"
        assert ('mail', 'A') not in rrsets, "mail muss gelöscht sein"

        # --- Schritt 4: Zurücksetzen auf minimalen Datensatz ------------------
        dj = self._upload_with_template(
            data_dir, self.MINIMAL, domain, require_api_token,
        )
        rrsets = self._get_rrset_map(dj, domain)
        assert ('@', 'NS') in rrsets
        assert ('@', 'A') not in rrsets, "A muss am Ende gelöscht sein"
        assert ('@', 'TXT') not in rrsets, "TXT muss am Ende gelöscht sein"


class TestCreateMissing:

    def test_bereits_vorhandene_domain_wird_nicht_neu_angelegt(
        self, data_dir, integration_config, require_api_token, require_test_domain
    ):
        """--create-missing legt keine bereits vorhandene Zone neu an."""
        dj = make_dnsjinja(
            data_dir, integration_config, require_api_token,
            create_missing=True,
        )

        # Die Zone existiert bereits → create() darf nicht aufgerufen worden sein
        # (wir können das nur indirekt prüfen: Domain muss normal befüllt sein)
        assert require_test_domain in dj._hetzner_zones


# ---------------------------------------------------------------------------
# Live-Sync mit den eingecheckten testdata/-Templates
# ---------------------------------------------------------------------------

class TestTestdataLiveSync:
    """Lädt mit den synthetischen testdata/-Templates eine vollständige Zone
    zur Testdomain hoch und verifiziert das Ergebnis über die RRSet-API.

    WARNUNG: Diese Tests überschreiben alle DNS-Records der Testdomain. Die
    autouse-Fixture `_reset_zone` setzt die Zone am Ende auf den minimalen
    Datensatz (nur NS) zurück.
    """

    FULL = {
        "template": "standard.tpl",
        "mail": "mailbox.org",
        "www": "bero",
        "xmpp": "mailbox",
        "custom_groups": ["demo-group"],
        "registrar": "Hetzner",
    }
    MINIMAL = {"template": "standard.tpl", "registrar": "Hetzner"}

    @staticmethod
    def _build(testdata_dir, tmp_path, token, domain, cfg, **kwargs):
        from tests.conftest import make_testdata_config
        import json
        config = make_testdata_config({domain: cfg})
        cfg_path = tmp_path / 'config.json'
        cfg_path.write_text(json.dumps(config), encoding='utf-8')
        return DNSJinja(
            datadir=str(testdata_dir),
            config_file=str(cfg_path),
            auth_api_token=token,
            **kwargs,
        )

    @staticmethod
    def _rrset_map(dj, domain):
        zone = dj._hetzner_zones[domain]
        return {
            (r.name, r.type): sorted(rec.value for rec in (r.records or []))
            for r in dj.client.zones.get_rrset_all(zone)
            if r.type != 'SOA'
        }

    @pytest.fixture(autouse=True)
    def _reset_zone(self, testdata_dir, tmp_path, require_api_token, require_test_domain):
        """Nach jedem Test: Zone auf den minimalen Datensatz zurücksetzen."""
        yield
        dj = self._build(testdata_dir, tmp_path, require_api_token,
                         require_test_domain, self.MINIMAL, upload=True)
        dj.upload_zone(require_test_domain)

    def test_full_feature_sync(
        self, testdata_dir, tmp_path, require_api_token, require_test_domain
    ):
        """Vollständige Feature-Zone wird hochgeladen und ist bei Hetzner sichtbar."""
        domain = require_test_domain
        dj = self._build(testdata_dir, tmp_path, require_api_token,
                         domain, self.FULL, upload=True)
        dj.upload_zone(domain)

        rr = self._rrset_map(dj, domain)
        # Mail
        assert ('@', 'MX') in rr
        assert any('mx1.mailprovider.example.' in v for v in rr[('@', 'MX')])
        assert ('autoconfig', 'CNAME') in rr
        assert ('_dmarc', 'TXT') in rr
        # Web
        assert rr[('@', 'A')] == ['192.0.2.10']
        assert rr[('www', 'A')] == ['192.0.2.10']
        # XMPP
        assert ('_xmpp-client._tcp', 'SRV') in rr
        # custom-group + per-domain custom include
        assert ('status', 'CNAME') in rr
        assert ('host1', 'A') in rr
        # registrar
        assert ('registrar', 'TXT') in rr

        # TTL aller verwalteten Records (außer dem von Hetzner gepflegten
        # SOA/NS-Satz) muss 300s betragen.
        zone = dj._hetzner_zones[domain]
        ttls = {
            r.ttl for r in dj.client.zones.get_rrset_all(zone)
            if r.type not in ('SOA', 'NS')
        }
        assert ttls == {300}, f"Unerwartete TTLs bei Hetzner: {ttls}"

    def test_reduzieren_entfernt_konfigurationsgesteuerte_rrsets(
        self, testdata_dir, tmp_path, require_api_token, require_test_domain
    ):
        """FULL → MINIMAL: konfigurationsgesteuerte Records (mail/www/xmpp/
        custom-groups) werden gelöscht; NS, registrar und der domänen-
        intrinsische custom/<domain>.inc bleiben erhalten.

        Hinweis: custom/<domain>.inc wird vom Template immer anhand des
        Domain-Namens eingebunden (ignore missing) – unabhängig von der
        Config. Für die Testdomain bleiben dessen Records daher bestehen.
        """
        domain = require_test_domain
        # Erst die volle Feature-Zone hochladen ...
        dj = self._build(testdata_dir, tmp_path, require_api_token,
                         domain, self.FULL, upload=True)
        dj.upload_zone(domain)
        assert ('@', 'MX') in self._rrset_map(dj, domain)

        # ... dann auf den minimalen Config-Datensatz reduzieren.
        dj = self._build(testdata_dir, tmp_path, require_api_token,
                         domain, self.MINIMAL, upload=True)
        dj.upload_zone(domain)

        rr = self._rrset_map(dj, domain)
        # Konfigurationsgesteuerte Features sind entfernt:
        assert ('@', 'MX') not in rr, "MX (mail) muss gelöscht sein"
        assert ('@', 'A') not in rr, "A (www) muss gelöscht sein"
        assert ('www', 'A') not in rr, "www muss gelöscht sein"
        assert ('_xmpp-client._tcp', 'SRV') not in rr, "XMPP muss gelöscht sein"
        assert ('status', 'CNAME') not in rr, "custom-group muss gelöscht sein"
        assert ('autoconfig', 'CNAME') not in rr, "mail-Records müssen gelöscht sein"
        # Persistente Records:
        assert ('@', 'NS') in rr
        assert ('registrar', 'TXT') in rr
        assert ('host1', 'A') in rr, "domänen-intrinsischer custom-Record bleibt"
