from jinja2 import Environment, FileSystemLoader
from socket import gethostbyname
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Required, TypedDict
import hcloud
from hcloud import Client
from hcloud.zones.domain import ZoneRecord
import json
import logging
import os
import re
import dns.name
import dns.rdatatype
import dns.resolver
import dns.exception
import dns.zone
import click
import sys
import pydantic
import tempfile
from .myloadenv import load_env
from .dnsjinja_config_schema import DnsJinjaConfig as _DnsJinjaConfigModel

logger = logging.getLogger(__name__)

_TEMPLATE_NAME_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


class DomainConfigEntry(TypedDict, total=False):
    """Laufzeit-Struktur eines Domain-Eintrags in self.config['domains']."""
    template: Required[str]   # aus config.json
    zone_file: str            # gesetzt von _prepare_zones() als 'zone-file'
    zone_id: str              # gesetzt von _prepare_zones() als 'zone-id'


class UploadError(Exception):
    pass


class DNSJinja:

    DEFAULT_API_BASE = "https://api.hetzner.cloud/v1"

    @staticmethod
    def _check_path(path: str, basedir: str, typ: str, expect: str = 'dir') -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(basedir) / p
        valid = p.is_dir() if expect == 'dir' else p.is_file()
        if not valid:
            kind = 'Verzeichnis' if expect == 'dir' else 'Datei'
            click.echo(f'{typ} {p} existiert nicht oder ist kein(e) {kind}.')
            sys.exit(1)
        return p

    def _prepare_zones(self) -> None:
        try:
            all_zones = self.client.zones.get_all()

            hetzner_zones = {z.name: z for z in all_zones}
            config_domains = set(self.config['domains'].keys())
            for d in sorted(config_domains - hetzner_zones.keys()):
                if self._create_missing:
                    try:
                        response = self.client.zones.create(name=d, mode="primary")
                        hetzner_zones[d] = response.zone
                        click.echo(f'{d} wurde neu bei Hetzner angelegt')
                    except hcloud.APIException as e:
                        click.echo(f'{d} konnte bei Hetzner nicht angelegt werden: {e} - wird ignoriert')
                        del self.config['domains'][d]
                else:
                    click.echo(f'{d} ist konfiguriert aber nicht bei Hetzner eingerichtet - wird ignoriert')
                    del self.config['domains'][d]
            for d in (hetzner_zones.keys() - config_domains):
                click.echo(f'{d} ist bei Hetzner eingerichtet aber nicht konfiguriert - bitte prüfen')
            for d in self.config['domains'].keys():
                self.config['domains'][d]['zone-id'] = hetzner_zones[d].id
                self.config['domains'][d]['zone-file'] = d + '.zone'
                self._hetzner_zones[d] = hetzner_zones[d]
        except (hcloud.HCloudException, OSError) as e:
            click.echo(f'Zonen bei Hetzner konnten nicht ermittelt werden: {e}')
            sys.exit(1)

    def __init__(self, upload: bool = False, backup: bool = False,
                 write_zone: bool = False, datadir: str = "",
                 config_file: str = "config/config.json",
                 auth_api_token: str = "", create_missing: bool = False) -> None:
        self.datadir = DNSJinja._check_path(datadir, '.', 'Datenverzeichnis', expect='dir')
        self.config_file = DNSJinja._check_path(config_file, '.', 'Konfigurationsdatei', expect='file')

        self.exit_status_file = Path(tempfile.gettempdir()) / f"dnsjinja.{os.getpid()}.exit.txt"
        self.exit_status_file.unlink(missing_ok=True)
        # Pointer-Datei aktualisieren, damit exit_on_error die aktuelle Exit-Code-Datei findet
        (Path(tempfile.gettempdir()) / "dnsjinja.exit.ptr").write_text(
            str(self.exit_status_file), encoding='utf-8'
        )

        try:
            with open(self.config_file, encoding='utf-8') as cfg_fh:
                self.config = json.load(cfg_fh)
            _DnsJinjaConfigModel.model_validate(self.config)
        except (json.JSONDecodeError, pydantic.ValidationError, OSError) as e:
            click.echo(f'Konfigurationsdatei {self.config_file} konnte nicht korrekt gelesen werden: {str(e)}')
            sys.exit(1)

        # noinspection PyTypeChecker
        self.templates_dir = DNSJinja._check_path(self.config['global']['templates'], self.datadir, 'Template-Verzeichnis', expect='dir')
        # noinspection PyTypeChecker
        self.zone_files_dir = DNSJinja._check_path(self.config['global']['zone-files'], self.datadir, 'Zone-File-Verzeichnis', expect='dir')
        # noinspection PyTypeChecker
        self.zone_backups_dir = DNSJinja._check_path(self.config['global']['zone-backups'], self.datadir, 'Zone-Backup-Verzeichnis', expect='dir')

        self.auth_api_token = auth_api_token
        if not self.auth_api_token:
            click.echo('Kein API-Token angegeben. Bitte --auth-api-token oder DNSJINJA_AUTH_API_TOKEN setzen.')
            sys.exit(1)
        self._api_base = self.config['global'].get('dns-api-base', self.DEFAULT_API_BASE).rstrip('/')
        self.client = Client(token=self.auth_api_token, api_endpoint=self._api_base)
        self._hetzner_zones: dict[str, Any] = {}
        self._create_missing: bool = create_missing

        self._prepare_zones()

        self._resolver = dns.resolver.Resolver(configure=False)
        self._resolver.nameservers = self.config["global"]["name-servers"]

        self._today = datetime.now(timezone.utc).strftime('%Y%m%d')
        self.upload = upload
        self.backup = backup
        self.write_zone = write_zone

        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.env.filters['hostname'] = gethostbyname
        self._serials: dict[str, str] = {}
        self.zones = self._create_zone_data()

    @property
    def today(self) -> str:
        return self._today

    def _get_zone_serial(self, domain: str) -> str:
        try:
            r = self._resolver.resolve(domain, "SOA")
            return str(r[0].serial)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                dns.resolver.NoNameservers, dns.exception.DNSException) as e:
            click.echo(f"Fehler beim Ermitteln des SOA-Zählers: {str(e)}")
            sys.exit(1)

    def _new_zone_serial(self, domain: str) -> str:
        soa_serial = self._get_zone_serial(domain)
        serial_prefix = soa_serial[:-2]
        if self.today == serial_prefix:
            suffix_int = int(soa_serial[-2:]) + 1
            if suffix_int > 99:
                click.echo(f'SOA-Zähler für {domain} hat 99 erreicht – kein weiterer Upload heute möglich.')
                sys.exit(1)
            serial_suffix = f'{suffix_int:02d}'
        else:
            serial_suffix = '01'
        return self.today + serial_suffix

    def _create_zone_data(self) -> dict[str, str]:
        zones: dict[str, str] = {}
        for domain, d in self.config["domains"].items():
            template_name = d["template"]
            if not _TEMPLATE_NAME_RE.fullmatch(template_name):
                click.echo(f'Ungültiger Template-Name: {template_name!r} – nur Buchstaben, Ziffern, . _ - erlaubt.')
                sys.exit(1)
            template = self.env.get_template(template_name)
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
                zonefile.write_text(self.zones[domain] + '\n', encoding='utf-8')
                click.echo(f'Domäne {domain} wurde erfolgreich geschrieben')
            except OSError as e:
                click.echo(f'Domäne {domain} konnte nicht geschrieben werden: {str(e)}')

    def _validate_zone_syntax(self, domain: str) -> None:
        try:
            dns.zone.from_text(self.zones[domain], origin=domain)
        except (dns.zone.UnknownOrigin, dns.exception.DNSException, Exception) as e:
            click.echo(f'Syntaxfehler im Zone-File für {domain}: {e}')
            sys.exit(1)

    def _parse_zone_rrsets(self, domain: str) -> dict[tuple[str, str], tuple[int, list[str]]]:
        """Parse gerenderten Zonentext in {(name, rdtype): (ttl, [rdata_values])}.

        SOA-Records werden ausgeschlossen (von Hetzner verwaltet).
        Hostnamen innerhalb der Zone werden relativ ausgegeben (wie Hetzner
        sie erwartet), externe FQDNs behalten den abschließenden Punkt.
        """
        origin = dns.name.from_text(domain)
        parsed = dns.zone.from_text(self.zones[domain], origin=origin)
        result: dict[tuple[str, str], tuple[int, list[str]]] = {}
        for name, node in parsed.nodes.items():
            rel_name = '@' if name == dns.name.empty else str(name)
            for rdataset in node.rdatasets:
                rdtype = dns.rdatatype.to_text(rdataset.rdtype)
                if rdtype == 'SOA':
                    continue
                ttl = int(rdataset.ttl)
                records = sorted(
                    r.to_text(origin=origin, relativize=True) for r in rdataset
                )
                result[(rel_name, rdtype)] = (ttl, records)
        return result

    def _sync_zone_rrsets(self, domain: str) -> None:
        """Synchronisiert gerenderte Zone-RRSets mit Hetzner über die Record-Level-API."""
        zone = self._hetzner_zones[domain]
        desired = self._parse_zone_rrsets(domain)

        current_rrsets = self.client.zones.get_rrset_all(zone)
        current_map: dict[tuple[str, str], Any] = {}
        for rrset in current_rrsets:
            if rrset.type == 'SOA':
                continue
            current_map[(rrset.name, rrset.type)] = rrset

        # Create / Update
        for (name, rdtype), (ttl, records) in desired.items():
            hetzner_records = [ZoneRecord(value=v) for v in records]
            key = (name, rdtype)

            if key in current_map:
                existing = current_map[key]
                if existing.protection and existing.protection.get('change'):
                    logger.warning('RRSet %s/%s ist geschützt, wird übersprungen', name, rdtype)
                    continue
                existing_values = sorted(r.value for r in (existing.records or []))
                if existing_values != records or existing.ttl != ttl:
                    self.client.zones.set_rrset_records(existing, hetzner_records)
                    if existing.ttl != ttl:
                        self.client.zones.change_rrset_ttl(existing, ttl)
            else:
                self.client.zones.create_rrset(
                    zone, name=name, type=rdtype, ttl=ttl, records=hetzner_records,
                )

        # Delete stale RRSets
        for (name, rdtype), rrset in current_map.items():
            if (name, rdtype) in desired:
                continue
            if rrset.protection and rrset.protection.get('change'):
                logger.warning('RRSet %s/%s ist geschützt, Löschung übersprungen', name, rdtype)
                continue
            try:
                self.client.zones.delete_rrset(rrset)
            except hcloud.APIException as e:
                logger.warning('RRSet %s/%s konnte nicht gelöscht werden: %s', name, rdtype, e)

    def upload_zone(self, domain: str) -> None:
        self._validate_zone_syntax(domain)
        try:
            self._sync_zone_rrsets(domain)
            click.echo(f'Domäne {domain} wurde bei Hetzner erfolgreich aktualisiert')
        except hcloud.APIException as e:
            self.exit_status_file.write_text("254", encoding='utf-8')
            raise UploadError(f'\nDomain: {domain}\nError Message: {e}')

    def upload_zones(self) -> None:
        if not self.upload:
            return
        for domain in self.config["domains"]:
            try:
                self.upload_zone(domain)
            except UploadError as e:
                click.echo(f'Domäne {domain} konnte bei Hetzner nicht aktualisiert werden: {str(e)}')
                continue

    def backup_zone(self, domain: str) -> None:
        try:
            zone = self._hetzner_zones[domain]
            response = self.client.zones.export_zonefile(zone)
            backupfile = self.zone_backups_dir / Path(self.config['domains'][domain]['zone-file'] + f'.{self._get_zone_serial(domain)}')
            backupfile.write_text(response.zonefile + '\n', encoding='utf-8')
            click.echo(f'Domäne {domain} wurde erfolgreich gesichert')
        except (hcloud.APIException, OSError) as e:
            click.echo(f'Domäne {domain} konnte nicht gesichert werden: {str(e)}')

    def backup_zones(self) -> None:
        if not self.backup:
            return
        for domain in self.config["domains"]:
            self.backup_zone(domain)

    def dry_run(self) -> None:
        """Gibt alle gerenderten Zone-Files auf stdout aus, ohne zu schreiben oder hochzuladen."""
        for domain, content in self.zones.items():
            click.echo(f'=== {domain} (Serial: {self._serials[domain]}) ===')
            click.echo(content)


@click.command()
@click.option('-d', '--datadir', default='.', envvar='DNSJINJA_DATADIR', show_default=True, help="Basisverzeichnis für Templates und Konfiguration (DNSJINJA_DATADIR)")
@click.option('-c', '--config', default='config/config.json', envvar='DNSJINJA_CONFIG', show_default=True, help="Konfigurationsdatei (DNSJINJA_CONFIG)")
@click.option('-u', '--upload', is_flag=True, default=False, help="Upload der Zonen")
@click.option('-b', '--backup', is_flag=True, default=False, help="Backup der Zonen")
@click.option('-w', '--write', is_flag=True, default=False, help="Zone-Files schreiben")
@click.option('-C', '--create-missing', is_flag=True, default=False, help="Konfigurierte Domains, die bei Hetzner nicht existieren, neu anlegen")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN', help="API-Token (Bearer) für Hetzner Cloud API (DNSJINJA_AUTH_API_TOKEN)")
@click.option('--dry-run', 'dry_run', is_flag=True, default=False, help="Zone-Files rendern und ausgeben, ohne zu schreiben oder hochzuladen")
def run(upload, backup, write, datadir, config, auth_api_token, create_missing, dry_run):
    """Modulare Verwaltung von DNS-Zonen (Hetzner Cloud API)"""
    if dry_run:
        dnsjinja = DNSJinja(False, False, False, datadir, config, auth_api_token, create_missing)
        dnsjinja.dry_run()
    else:
        dnsjinja = DNSJinja(upload, backup, write, datadir, config, auth_api_token, create_missing)
        dnsjinja.backup_zones()
        dnsjinja.write_zone_files()
        dnsjinja.upload_zones()


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format='%(levelname)s: %(message)s',
    )
    load_env()
    run()


if __name__ == '__main__':

    sys.tracebacklimit = 0
    main()
