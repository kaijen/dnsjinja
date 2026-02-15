from jinja2 import Environment, FileSystemLoader
from socket import gethostbyname
from pathlib import Path
from datetime import datetime, timezone
import hcloud
from hcloud import Client
import json
import os
import dns.resolver
import dns.exception
import click
import sys
import jsonschema
import tempfile
from .myloadenv import load_env
from .dnsjinja_config_schema import DNSJINJA_JSON_SCHEMA


class UploadError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.msgfmt = message


class DNSJinja:

    DEFAULT_API_BASE = "https://api.hetzner.cloud/v1"

    @staticmethod
    def _check_dir(path_to_check: str, basedir: str, typ: str) -> Path:
        path_to_check = Path(path_to_check)
        if not path_to_check.is_absolute():
            path_to_check = Path(basedir) / path_to_check
        if not path_to_check.is_dir():
            print(f'{typ} {path_to_check} existiert nicht oder ist kein Verzeichnis.')
            sys.exit(1)
        return path_to_check

    @staticmethod
    def _check_file(path_to_check: str, basedir: str, typ: str) -> Path:
        path_to_check = Path(path_to_check)
        if not path_to_check.is_absolute():
            path_to_check = Path(basedir) / path_to_check
        if not path_to_check.is_file():
            print(f'{typ} {path_to_check} existiert nicht oder ist keine Datei.')
            sys.exit(1)
        return path_to_check

    def _prepare_zones(self) -> None:
        try:
            all_zones = self.client.zones.get_all()

            hetzner_domains = set(z.name for z in all_zones)
            config_domains = set(self.config['domains'].keys())
            hetzner_zones = {z.name: z for z in all_zones}
            for d in sorted(config_domains - hetzner_domains):
                if self._create_missing:
                    try:
                        response = self.client.zones.create(name=d, mode="primary")
                        hetzner_zones[d] = response.zone
                        print(f'{d} wurde neu bei Hetzner angelegt')
                    except hcloud.APIException as e:
                        print(f'{d} konnte bei Hetzner nicht angelegt werden: {e} - wird ignoriert')
                        del self.config['domains'][d]
                else:
                    print(f'{d} ist konfiguriert aber nicht bei Hetzner eingerichtet - wird ignoriert')
                    del self.config['domains'][d]
            for d in (hetzner_domains - config_domains):
                print(f'{d} ist bei Hetzner eingerichtet aber nicht konfiguriert - bitte prüfen')
            for d in self.config['domains'].keys():
                self.config['domains'][d]['zone-id'] = hetzner_zones[d].id
                self.config['domains'][d]['zone-file'] = d + '.zone'
                self._hetzner_zones[d] = hetzner_zones[d]
        except (hcloud.HCloudException, OSError) as e:
            print(f'Zonen bei Hetzner konnten nicht ermittelt werden: {e}')
            sys.exit(1)

    def __init__(self, upload=False, backup=False, write_zone=False, datadir="", config_file="config/config.json", auth_api_token="", create_missing=False):
        self.datadir = DNSJinja._check_dir(datadir, '.', 'Datenverzeichnis')
        self.config_file = DNSJinja._check_file(config_file, '.', 'Konfigurationsdatei')

        self.exit_status_file = Path(tempfile.gettempdir()) / f"dnsjinja.{os.getpid()}.exit.txt"
        self.exit_status_file.unlink(missing_ok=True)
        # Pointer-Datei aktualisieren, damit exit_on_error die aktuelle Exit-Code-Datei findet
        (Path(tempfile.gettempdir()) / "dnsjinja.exit.ptr").write_text(
            str(self.exit_status_file), encoding='utf-8'
        )

        self.config_schema = DNSJINJA_JSON_SCHEMA

        try:
            with open(self.config_file, encoding='utf-8') as cfg_fh:
                self.config = json.load(cfg_fh)
            jsonschema.validate(self.config, self.config_schema, cls=jsonschema.Draft7Validator)
        except (json.JSONDecodeError, jsonschema.ValidationError, OSError) as e:
            print(f'Konfigurationsdatei {self.config_file} konnte nicht korrekt gelesen werden: {str(e)}')
            sys.exit(1)

        # noinspection PyTypeChecker
        self.templates_dir = DNSJinja._check_dir(self.config['global']['templates'], self.datadir, 'Template-Verzeichnis')
        # noinspection PyTypeChecker
        self.zone_files_dir = DNSJinja._check_dir(self.config['global']['zone-files'], self.datadir, 'Zone-File-Verzeichnis')
        # noinspection PyTypeChecker
        self.zone_backups_dir = DNSJinja._check_dir(self.config['global']['zone-backups'], self.datadir, 'Zone-Backup-Verzeichnis')

        self.auth_api_token = auth_api_token
        if not self.auth_api_token:
            print('Kein API-Token angegeben. Bitte --auth-api-token oder DNSJINJA_AUTH_API_TOKEN setzen.')
            sys.exit(1)
        self._api_base = self.config['global'].get('dns-api-base', self.DEFAULT_API_BASE).rstrip('/')
        self.client = Client(token=self.auth_api_token, api_endpoint=self._api_base)
        self._hetzner_zones = {}
        self._create_missing = create_missing

        self._prepare_zones()

        self._resolver = dns.resolver.Resolver(configure=False)
        self._resolver.nameservers = self.config["global"]["name-servers"]

        self._today = datetime.now(timezone.utc).strftime('%Y%m%d')
        self._upload = upload
        self._backup = backup
        self._write_zone = write_zone

        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.env.filters['hostname'] = gethostbyname
        self._serials: dict = {}
        self.zones = self._create_zone_data()

    @property
    def today(self) -> str:
        return self._today

    @property
    def upload(self) -> bool:
        return self._upload

    @upload.setter
    def upload(self, new_status: bool) -> None:
        self._upload = new_status

    @property
    def backup(self) -> bool:
        return self._backup

    @backup.setter
    def backup(self, new_status: bool) -> None:
        self._backup = new_status

    @property
    def write_zone(self) -> bool:
        return self._write_zone

    @write_zone.setter
    def write_zone(self, new_status: bool) -> None:
        self._write_zone = new_status

    def _get_zone_serial(self, domain: str) -> str:
        try:
            r = self._resolver.resolve(domain, "SOA")
            return str(r[0].serial)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                dns.resolver.NoNameservers, dns.exception.DNSException) as e:
            print(f"Fehler beim Ermitteln des SOA-Zählers: {str(e)}")
            sys.exit(1)

    def _new_zone_serial(self, domain: str) -> str:
        soa_serial = self._get_zone_serial(domain)
        serial_prefix = soa_serial[:-2]
        if self.today == serial_prefix:
            suffix_int = int(soa_serial[-2:]) + 1
            if suffix_int > 99:
                print(f'SOA-Zähler für {domain} hat 99 erreicht – kein weiterer Upload heute möglich.')
                sys.exit(1)
            serial_suffix = f'{suffix_int:02d}'
        else:
            serial_suffix = '01'
        return self.today + serial_suffix

    def _create_zone_data(self) -> dict:
        zones = {}
        for domain, d in self.config["domains"].items():
            template = self.env.get_template(d["template"])
            soa_serial = self._new_zone_serial(domain)
            self._serials[domain] = soa_serial
            zones[domain] = template.render(domain=domain, soa_serial=soa_serial, **d)
        return zones

    def write_zone_files(self) -> None:
        if not self.write_zone:
            return
        for domain, d in self.config["domains"].items():
            zonefile = self.zone_files_dir / Path(d['zone-file'] + f'.{self._serials[domain]}')
            try:
                with open(zonefile, 'w', encoding='utf-8') as zf:
                    print(self.zones[domain], file=zf)
                print(f'Domäne {domain} wurde erfolgreich geschrieben')
            except OSError as e:
                print(f'Domäne {domain} konnte nicht geschrieben werden: {str(e)}')

    def upload_zone(self, domain: str) -> None:
        zone = self._hetzner_zones[domain]
        try:
            self.client.zones.import_zonefile(zone, self.zones[domain])
            print(f'Domäne {domain} wurde bei Hetzner erfolgreich aktualisiert')
        except hcloud.APIException as e:
            with open(self.exit_status_file, "w", encoding="utf8") as exit_code_file:
                exit_code_file.write("254")
            raise UploadError(f'\nDomain: {domain}\nError Message: {e}')

    def upload_zones(self) -> None:
        if not self.upload:
            return
        for domain, d in self.config["domains"].items():
            try:
                self.upload_zone(domain)
            except UploadError as e:
                print(f'Domäne {domain} konnte bei Hetzner nicht aktualisiert werden: {str(e)}')
                continue

    def backup_zone(self, domain: str) -> None:
        try:
            zone = self._hetzner_zones[domain]
            response = self.client.zones.export_zonefile(zone)
            backupfile = self.zone_backups_dir / Path(self.config['domains'][domain]['zone-file'] + f'.{self._get_zone_serial(domain)}')
            with open(backupfile, 'w', encoding='utf-8') as zf:
                print(response.zonefile, file=zf)
            print(f'Domäne {domain} wurde erfolgreich gesichert')
        except (hcloud.APIException, OSError) as e:
            print(f'Domäne {domain} konnte nicht gesichert werden: {str(e)}')

    def backup_zones(self) -> None:
        if not self.backup:
            return
        for domain, d in self.config["domains"].items():
            self.backup_zone(domain)


@click.command()
@click.option('-d', '--datadir', default='.', envvar='DNSJINJA_DATADIR', show_default=True, help="Basisverzeichnis für Templates und Konfiguration (DNSJINJA_DATADIR)")
@click.option('-c', '--config', default='config/config.json', envvar='DNSJINJA_CONFIG', show_default=True, help="Konfigurationsdatei (DNSJINJA_CONFIG)")
@click.option('-u', '--upload', is_flag=True, default=False, help="Upload der Zonen")
@click.option('-b', '--backup', is_flag=True, default=False, help="Backup der Zonen")
@click.option('-w', '--write', is_flag=True, default=False, help="Zone-Files schreiben")
@click.option('-C', '--create-missing', is_flag=True, default=False, help="Konfigurierte Domains, die bei Hetzner nicht existieren, neu anlegen")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN', help="API-Token (Bearer) für Hetzner Cloud API (DNSJINJA_AUTH_API_TOKEN)")
def run(upload, backup, write, datadir, config, auth_api_token, create_missing):
    """Modulare Verwaltung von DNS-Zonen (Hetzner Cloud API)"""
    dnsjinja = DNSJinja(upload, backup, write, datadir, config, auth_api_token, create_missing)
    dnsjinja.backup_zones()
    dnsjinja.write_zone_files()
    dnsjinja.upload_zones()


def main():
    load_env()
    run()


if __name__ == '__main__':

    sys.tracebacklimit = 0
    main()
