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
