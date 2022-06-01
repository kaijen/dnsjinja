from jinja2 import Environment, FileSystemLoader
from socket import gethostbyname
from pathlib import Path
from datetime import datetime
import requests
import json
import dns.resolver
import click
import sys
import jsonschema
from .myloadenv import load_env
from .dnsjinja_config_schema import DNSJINJA_JSON_SCHEMA

# TODO Klassen für MagicConfig und MagicEnv mit abstrakter Basisklasse MagicSetupBase
#      appdirs
#      python-dotenv
#      jsonschema
#      Magische Pfade nutzen, Paramter für *all* oder *first*
#      So viel Funktionalität wie möglich in der Basisklasse implementieren
#      Pfade ermitteln und zurückliefern
#      Environment laden
#      Environment als JSON (?)
#      Environment als dict
#      Config als JSON
#      Config als dict

# TODO pydantic nutzen

# TODO Mit PyScaffold für pip Installation vorbereiten (aus github/gitlab installieren)
#      https://stackoverflow.com/questions/4830856/is-it-possible-to-use-pip-to-install-a-package-from-a-private-github-repository


# TODO Klären warum die Validierung der Konfiguration gegen das Schema nicht fehlschlägt

class DNSJinja:
    
    @staticmethod
    def _check_dir(path_to_check: str, basedir: str, typ: str) -> Path:
        path_to_check = Path(path_to_check)
        if not path_to_check.is_absolute():
            path_to_check = Path(basedir) / path_to_check
        if not path_to_check.exists():
            print(f'{typ} {path_to_check} existiert nicht.')
            sys.exit(1)
        return path_to_check

    def _prepare_zones(self) -> None:
        try:
            response = requests.get(
                url=self.config['global']['dns-zones-api'],
                headers={
                    "Auth-API-Token": self.auth_api_token,
                },
            )
            if response.status_code == 200:
                r = response.json()
                hetzner_domains = set([z['name'] for z in r['zones']])
                config_domains = set(self.config['domains'].keys())
                hetzner_ids = {z['name']: z['id'] for z in r['zones']}
                for d in (config_domains - hetzner_domains):
                    print(f'{d} ist konfiguriert aber nicht bei Hetzner eingerichtet - wird ignoriert')
                    del self.config['domains'][d]
                for d in (hetzner_domains - config_domains):
                    print(f'{d} ist bei Hetzner eingerichtet aber nicht konfiguriert - bitte prüfen')
                for d in self.config['domains'].keys():
                    self.config['domains'][d]['zone-id'] = hetzner_ids[d]
                    self.config['domains'][d]['zone-file'] = d + '.zone'
            else:
                print(f'{response.url}: {response.status_code}')
                print('Zonen bei Hetzner konnten nicht ermittelt werden.')
                sys.exit(1)
        except requests.exceptions.RequestException:
            print('Zonen bei Hetzner konnten nicht ermittelt werden.')
            sys.exit(1)

    def __init__(self, upload=False, backup=False, write_zone=False, datadir="", config_file="config/config.json", auth_api_token=""):
        self.datadir = DNSJinja._check_dir(datadir, '.', 'Datenverzeichnis')
        self.config_file = DNSJinja._check_dir(config_file, '.', 'Konfigurationsdatei')

        self.config_schema = DNSJINJA_JSON_SCHEMA

        try:
            with open(self.config_file, encoding='utf-8') as config_file:
                self.config = json.load(config_file)
            jsonschema.validate(self.config, self.config_schema)
        except Exception as e:
            print(f'Konfigurationsdatei {config_file} konnte nicht korrekt gelesen werden: {str(e)}')
            sys.exit(1)

        # noinspection PyTypeChecker
        self.templates_dir = DNSJinja._check_dir(self.config['global']['templates'], self.datadir, 'Template-Verzeichnis')
        # noinspection PyTypeChecker
        self.zone_files_dir = DNSJinja._check_dir(self.config['global']['zone-files'], self.datadir, 'Zone-File-Verzeichnis')
        # noinspection PyTypeChecker
        self.zone_backups_dir = DNSJinja._check_dir(self.config['global']['zone-backups'], self.datadir, 'Zone-Backup-Verzeichnis')

        self.auth_api_token = auth_api_token

        self._prepare_zones()

        self._today = datetime.utcnow().strftime('%Y%m%d')
        self._upload = upload
        self._backup = backup
        self._write_zone = write_zone

        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.env.filters['hostname'] = gethostbyname
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
        hetzner_resolver = dns.resolver.Resolver(configure=False)
        hetzner_resolver.nameservers = self.config["global"]["name-servers"]
        try:
            r = hetzner_resolver.resolve(domain, "SOA")
            return str(r[0].serial)
        except Exception as e:
            print(f"Fehler beim Ermitteln des SOA-Zählers: {str(e)}")
            sys.exit(1)

    def _new_zone_serial(self, domain: str) -> str:
        soa_serial = self._get_zone_serial(domain)
        serial_prefix = soa_serial[:-2]
        if self.today == serial_prefix:
            serial_suffix = f'{int(soa_serial[-2:])+1:02d}'
        else:
            serial_suffix = '01'
        return self.today + serial_suffix

    def _create_zone_data(self) -> dict:
        zones = {}
        for domain, d in self.config["domains"].items():
            template = self.env.get_template(d["template"])
            zones[domain] = template.render(domain=domain, soa_serial=self._new_zone_serial(domain), **d)
        return zones

    def write_zone_files(self) -> None:
        if not self.write_zone:
            return
        for domain, d in self.config["domains"].items():
            zonefile = self.zone_files_dir / Path(d['zone-file'] + f'.{self._new_zone_serial(domain)}')
            try:
                with open(zonefile, 'w', encoding='utf-8') as zf:
                    print(self.zones[domain], file=zf)
                    print(f'Domäne {domain} wurde erfolgreich geschrieben')
            except Exception as e:
                print(f'Domäne {domain} konnte nicht geschrieben werden: {str(e)}')

    def upload_zone(self, domain: str) -> None:
        url = self.config["global"]["dns-upload-api"].replace("{ZoneID}", self.config['domains'][domain]['zone-id'])
        try:
            response = requests.post(
                url=url,
                headers={
                    "Content-Type": "text/plain",
                    "Auth-API-Token": self.auth_api_token
                },
                data=self.zones[domain]
            )
            if response.status_code == 200:
                print(f'Domäne {domain} wurde bei Hetzner erfolgreich aktualisiert')
            else:
                raise Exception(f'HTTP-Response-Code {response.status_code}')
                # print(f'{domain}: Problem mit HTTP-Request {url}: {response.status_code}')
        except requests.exceptions.RequestException as e:
            print(f'Domäne {domain} konnte bei Hetzner nicht aktualisiert werden: {str(e)}')

    def upload_zones(self) -> None:
        if not self.upload:
            return
        if not self.auth_api_token:
            self.auth_api_token = input("Auth-API-Token: ")
        for domain, d in self.config["domains"].items():
            self.upload_zone(domain)

    def backup_zone(self, domain: str) -> None:
        try:
            url = self.config["global"]["dns-download-api"].replace("{ZoneID}", self.config['domains'][domain]['zone-id'])
            response = requests.get(
                url=url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                    "Auth-API-Token": self.auth_api_token
                },
                data={}
            )
            if response.status_code == 200:
                backupfile = self.zone_backups_dir / Path(self.config['domains'][domain]['zone-file'] + f'.{self._get_zone_serial(domain)}')
                with open(backupfile, 'w', encoding='utf-8') as zf:
                    print(response.text, file=zf)
                print(f'Domäne {domain} wurde erfolgreich gesichert')
            else:
                raise Exception(f'HTTP-Response-Code {response.status_code}')
                # print(f'{domain}: Problem mit HTTP-Request {url}: {response.status_code}')
        except Exception as e:
            print(f'Domäne {domain} konnte nicht gesichert werden: {str(e)}')

    def backup_zones(self) -> None:
        if not self.backup:
            return
        if not self.auth_api_token:
            self.auth_api_token = input("Auth-API-Token: ")
        for domain, d in self.config["domains"].items():
            self.backup_zone(domain)


@click.command()
@click.option('-d', '--datadir', default='.', envvar='DNSJINJA_DATADIR', show_default=True, help="Basisverzeichnis für Templates und Konfiguration (DNSJINJA_DATADIR)")
@click.option('-c', '--config', default='config/config.json', envvar='DNSJINJA_CONFIG', show_default=True, help="Konfigurationsdatei (DNSJINJA_CONFIG)")
@click.option('-u', '--upload', is_flag=True, default=False, help="Upload der Zonen")
@click.option('-b', '--backup', is_flag=True, default=False, help="Backup der Zonen")
@click.option('-w', '--write', is_flag=True, default=False, help="Zone-Files schreiben")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN', help="AUTH-API-TOKEN für REST-API (DNSJINJA_AUTH_API_TOKEN)")
def run(upload, backup, write, datadir, config, auth_api_token):
    """Modulare Verwaltung von DNS-Zonen"""
    dnsjinja = DNSJinja(upload, backup, write, datadir, config, auth_api_token)
    dnsjinja.backup_zones()
    dnsjinja.write_zone_files()
    dnsjinja.upload_zones()


def main():
    load_env()
    run()


if __name__ == '__main__':

    main()
