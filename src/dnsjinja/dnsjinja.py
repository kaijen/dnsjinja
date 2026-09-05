from jinja2 import Environment, FileSystemLoader
from socket import gethostbyname
from pathlib import Path
from datetime import datetime, timezone
from typing import Required, TypedDict
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
from .backends import (
    BackendError,
    DNSBackend,
    RRSet,
    RRSetChange,
    UnknownBackendError,
    Zone,
    available_backends,
    create_backend,
    get_backend_class,
)

logger = logging.getLogger(__name__)

_TEMPLATE_NAME_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


class DomainConfigEntry(TypedDict, total=False):
    """Laufzeit-Struktur eines Domain-Eintrags in self.config['domains']."""
    template: Required[str]   # aus config.json
    zone_file: str            # gesetzt von _prepare_zones() als 'zone-file'
    zone_id: str              # gesetzt von _prepare_zones() als 'zone-id'


class UploadError(Exception):
    pass


# RRSetChange lebt in backends.base, weil DNSBackend.apply_changes() sie als
# Parametertyp braucht. Hier re-exportiert, damit bestehende Importe aus
# dnsjinja.dnsjinja weiter funktionieren.
__all__ = ['DNSJinja', 'RRSetChange', 'UploadError', 'main', 'run']


class DNSJinja:

    DEFAULT_BACKEND = 'hetzner'

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
        label = self._backend_label
        try:
            remote_zones = self.backend.list_zones()

            config_domains = set(self.config['domains'].keys())
            for d in sorted(config_domains - remote_zones.keys()):
                if self._create_missing and self.backend.capabilities.supports_zone_create:
                    try:
                        remote_zones[d] = self.backend.create_zone(d)
                        click.echo(f'{d} wurde neu {label} angelegt')
                    except BackendError as e:
                        click.echo(f'{d} konnte {label} nicht angelegt werden: {e} - wird ignoriert')
                        del self.config['domains'][d]
                else:
                    click.echo(f'{d} ist konfiguriert aber nicht {label} eingerichtet - wird ignoriert')
                    del self.config['domains'][d]
            for d in (remote_zones.keys() - config_domains):
                click.echo(f'{d} ist {label} eingerichtet aber nicht konfiguriert - bitte prüfen')
            for d in self.config['domains'].keys():
                self.config['domains'][d]['zone-id'] = remote_zones[d].zone_id
                self.config['domains'][d]['zone-file'] = d + '.zone'
                self._zones[d] = remote_zones[d]
        except (BackendError, OSError) as e:
            click.echo(f'Zonen {label} konnten nicht ermittelt werden: {e}')
            sys.exit(1)

    def _resolve_backend(self, auth_api_token: str) -> None:
        """Ermittelt Backend-Name, Basis-URL und Token und erzeugt das Backend.

        Der Backend-Name steht in der config.json, die Tokenauflösung hängt
        davon ab – deshalb passiert beides hier und nicht in run().
        """
        global_cfg = self.config['global']
        backend_name = global_cfg.get('dns-backend', self.DEFAULT_BACKEND)
        try:
            backend_cls = get_backend_class(backend_name)
        except UnknownBackendError as e:
            click.echo(str(e))
            sys.exit(1)

        self.backend_name = backend_name
        self._backend_label = f'beim Backend {backend_name}'

        # Priorität: CLI-Option, backendspezifische Variable, allgemeine Variable.
        env_specific = f'DNSJINJA_{backend_name.upper().replace("-", "_")}_AUTH_API_TOKEN'
        self.auth_api_token = (
            auth_api_token
            or os.environ.get(env_specific, '')
            or os.environ.get('DNSJINJA_AUTH_API_TOKEN', '')
        )
        if not self.auth_api_token:
            click.echo(
                'Kein API-Token angegeben. Bitte --auth-api-token, '
                f'{env_specific} oder DNSJINJA_AUTH_API_TOKEN setzen.'
            )
            sys.exit(1)

        self._api_base = (
            global_cfg.get('dns-api-base') or backend_cls.default_api_base
        ).rstrip('/')
        self.backend: DNSBackend = create_backend(
            backend_name, token=self.auth_api_token, api_base=self._api_base,
            options=global_cfg.get('backend-options', {}),
        )

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

        self._zones: dict[str, Zone] = {}
        self._create_missing: bool = create_missing
        self._resolve_backend(auth_api_token)

        self._prepare_zones()

        self._resolver = dns.resolver.Resolver(configure=False)
        self._resolver.nameservers = self.config["global"]["name-servers"]
        self._dns_serials: dict[str, str | None] = {}

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

    def _get_zone_serial(self, domain: str) -> str | None:
        """Ermittelt den SOA-Zähler per DNS.

        Gibt None zurück, wenn die Zone nicht auflösbar ist. Das ist bei einer frisch
        angelegten Domäne der Normalfall: Sie muss beim Backend existieren, bevor sie
        registriert und delegiert werden kann, und antwortet bis dahin mit REFUSED.
        """
        if domain in self._dns_serials:
            return self._dns_serials[domain]
        try:
            r = self._resolver.resolve(domain, "SOA")
            serial: str | None = str(r[0].serial)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                dns.resolver.NoNameservers, dns.exception.DNSException) as e:
            click.echo(f"SOA-Zähler für {domain} konnte nicht per DNS ermittelt werden "
                       f"(Domäne noch nicht delegiert?): {str(e)}")
            serial = None
        self._dns_serials[domain] = serial
        return serial

    def _new_zone_serial(self, domain: str) -> str:
        """Bildet den nächsten SOA-Zähler im Format YYYYMMDDNN.

        Der per DNS geholte Zähler muss dieses Format nicht haben: Anbieter, die
        den SOA-Record selbst pflegen, zählen anders. Ein unlesbarer Zähler
        beginnt deshalb den heutigen Tag neu, statt den Lauf abzubrechen – der
        Zähler steckt nur in Dateinamen und im gerenderten Text, nicht in dem,
        was hochgeladen wird.
        """
        soa_serial = self._get_zone_serial(domain)
        if soa_serial is None:
            return self.today + '01'
        serial_prefix = soa_serial[:-2]
        if self.today == serial_prefix:
            try:
                suffix_int = int(soa_serial[-2:]) + 1
            except ValueError:
                click.echo(f'SOA-Zähler {soa_serial!r} für {domain} folgt nicht dem Format '
                           'YYYYMMDDNN – der Zähler beginnt heute neu bei 01.')
                return self.today + '01'
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

        SOA-Records werden ausgeschlossen (vom Anbieter verwaltet).
        Owner-Namen werden relativ ausgegeben (inkl. '@' für den Apex, wie
        die Backends sie erwarten). RDATA-Ziele werden als FQDN ausgegeben,
        damit ein CNAME-Ziel auf den Zonen-Apex nicht zu '@' kollabiert – Hetzner
        lehnt '@' als CNAME-Wert mit invalid_input ab, deSEC verlangt für
        CNAME/MX/NS/SRV ebenfalls absolute Namen.
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
                    r.to_text(origin=origin, relativize=False) for r in rdataset
                )
                result[(rel_name, rdtype)] = (ttl, records)
        return result

    def _plan_zone_rrsets(self, domain: str) -> list[RRSetChange]:
        """Vergleicht die gerenderte Zone mit den Live-Daten des Backends.

        Liefert die geplanten Änderungen, ohne etwas zu verändern. Basis sowohl
        für _sync_zone_rrsets() (Ausführung) als auch für dry_run_compare()
        (Anzeige) – so können Anzeige und Ausführung nicht auseinanderlaufen.

        Die Normalisierung auf die Grenzen des Backends (TTL, nicht schreibbare
        RR-Typen, RDATA-Form) passiert hier und damit für beide Pfade gemeinsam.
        Läge sie später, zeigte der Trockenlauf andere Daten als der Upload
        schreibt.
        """
        zone = self._zones[domain]
        desired, warnings = self.backend.normalize_desired(
            zone, self._parse_zone_rrsets(domain)
        )
        for warning in warnings:
            logger.warning('%s: %s', domain, warning)

        current_map = {r.key: r for r in self.backend.list_rrsets(zone)}

        changes: list[RRSetChange] = []

        # Create / Update
        for key, want in desired.items():
            name, rdtype = key
            existing = current_map.get(key)
            if existing is None:
                changes.append(RRSetChange('create', name, rdtype,
                                           ttl=want.ttl, records=list(want.records)))
                continue
            existing_values = list(existing.records)
            common = dict(ttl=want.ttl, records=list(want.records),
                          current_ttl=existing.ttl, current_records=existing_values,
                          current=existing)
            if existing.protected:
                changes.append(RRSetChange('protected', name, rdtype, **common))
            elif existing_values != list(want.records) or existing.ttl != want.ttl:
                changes.append(RRSetChange('update', name, rdtype, **common))
            else:
                changes.append(RRSetChange('unchanged', name, rdtype, **common))

        # Delete stale RRSets
        for key, existing in current_map.items():
            if key in desired:
                continue
            name, rdtype = key
            action = 'protected' if existing.protected else 'delete'
            changes.append(RRSetChange(action, name, rdtype,
                                       current_ttl=existing.ttl,
                                       current_records=list(existing.records),
                                       current=existing))

        return changes

    def _sync_zone_rrsets(self, domain: str) -> None:
        """Übergibt den Änderungsplan an das Backend."""
        zone = self._zones[domain]

        actionable: list[RRSetChange] = []
        for change in self._plan_zone_rrsets(domain):
            if change.action == 'protected':
                logger.warning('RRSet %s/%s ist geschützt, wird übersprungen',
                               change.name, change.rdtype)
            elif change.action in ('create', 'update', 'delete'):
                actionable.append(change)

        result = self.backend.apply_changes(zone, actionable)
        for warning in result.warnings:
            logger.warning('%s: %s', domain, warning)
        for change, reason in result.skipped:
            click.echo(f'  RRSet {change.name}/{change.rdtype} übersprungen: {reason}')
        self._last_apply_skipped = len(result.skipped)

    def upload_zone(self, domain: str) -> None:
        self._validate_zone_syntax(domain)
        self._last_apply_skipped = 0
        try:
            self._sync_zone_rrsets(domain)
        except BackendError as e:
            self.exit_status_file.write_text("254", encoding='utf-8')
            raise UploadError(f'\nDomain: {domain}\nError Message: {e}')
        if self._last_apply_skipped:
            click.echo(f'Domäne {domain} wurde {self._backend_label} mit Einschränkungen '
                       f'aktualisiert ({self._last_apply_skipped} übersprungen)')
        else:
            click.echo(f'Domäne {domain} wurde {self._backend_label} erfolgreich aktualisiert')

    def upload_zones(self) -> None:
        if not self.upload:
            return
        for domain in self.config["domains"]:
            try:
                self.upload_zone(domain)
            except UploadError as e:
                click.echo(f'Domäne {domain} konnte {self._backend_label} nicht '
                           f'aktualisiert werden: {str(e)}')
                continue

    def backup_zone(self, domain: str) -> None:
        if not self.backend.capabilities.supports_zonefile_export:
            click.echo(f'Domäne {domain} kann nicht gesichert werden: Backend '
                       f'{self.backend_name} kennt keinen Zonefile-Export')
            return
        try:
            zone = self._zones[domain]
            zonefile = self.backend.export_zonefile(zone)
            serial = self._get_zone_serial(domain) or self._serials[domain]
            backupfile = self.zone_backups_dir / Path(self.config['domains'][domain]['zone-file'] + f'.{serial}')
            backupfile.write_text(zonefile + '\n', encoding='utf-8')
            click.echo(f'Domäne {domain} wurde erfolgreich gesichert')
        except (BackendError, OSError) as e:
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

    @staticmethod
    def _echo_change(change: RRSetChange, show_ttl: bool = False) -> None:
        label = f'{change.name}/{change.rdtype}'
        if change.action == 'create':
            click.echo(f'  + {label}  (TTL {change.ttl})')
            for v in change.records:
                click.echo(f'      + {v}')
        elif change.action == 'delete':
            click.echo(f'  - {label}  (TTL {change.current_ttl})')
            for v in change.current_records:
                click.echo(f'      - {v}')
        elif change.action == 'update':
            if show_ttl and change.current_ttl != change.ttl:
                ttl_info = f'TTL {change.current_ttl} -> {change.ttl}'
            else:
                ttl_info = f'TTL {change.current_ttl}'
            click.echo(f'  ~ {label}  ({ttl_info})')
            for v in change.current_records:
                if v not in change.records:
                    click.echo(f'      - {v}')
            for v in change.records:
                if v not in change.current_records:
                    click.echo(f'      + {v}')
        elif change.action == 'protected':
            click.echo(f'  ! {label}  geschützt – wird beim Upload übersprungen')

    def dry_run_compare(self, show_ttl: bool = False) -> None:
        """Zeigt die Unterschiede zwischen Live-Daten des Backends und Templates an.

        Reine TTL-Abweichungen werden ohne show_ttl ausgeblendet, weil die TTL in
        den Templates nicht pro Record gesetzt, sondern global über $TTL vererbt
        wird. Der Upload gleicht sie trotzdem an – darauf weist die Zusammenfassung
        ausdrücklich hin, damit Anzeige und Upload nicht stillschweigend abweichen.
        """
        for domain in self.config['domains']:
            click.echo(f'=== {domain} ===')
            self._validate_zone_syntax(domain)
            try:
                changes = self._plan_zone_rrsets(domain)
            except (BackendError, OSError) as e:
                click.echo(f'  Live-Daten konnten nicht gelesen werden: {e}')
                continue

            counts = {a: 0 for a in ('create', 'update', 'delete', 'protected', 'unchanged')}
            ttl_only = 0
            for change in sorted(changes, key=lambda c: (c.name, c.rdtype)):
                counts[change.action] += 1
                if change.ttl_only:
                    ttl_only += 1
                    if not show_ttl:
                        continue
                self._echo_change(change, show_ttl)

            shown = counts['create'] + counts['delete'] + counts['protected'] + counts['update']
            if not show_ttl:
                shown -= ttl_only
            if not shown:
                click.echo('  Keine Unterschiede')
            click.echo(
                f'  {counts["create"]} neu, {counts["update"]} geändert, '
                f'{counts["delete"]} gelöscht, {counts["protected"]} geschützt, '
                f'{counts["unchanged"]} unverändert'
            )
            if ttl_only and not show_ttl:
                click.echo(
                    f'  Hinweis: {ttl_only} RRSet(s) weichen nur in der TTL ab. Sie sind oben '
                    'ausgeblendet, werden beim Upload aber angeglichen – mit --show-ttl anzeigen.'
                )


@click.command()
@click.option('-d', '--datadir', default='.', envvar='DNSJINJA_DATADIR', show_default=True, help="Basisverzeichnis für Templates und Konfiguration (DNSJINJA_DATADIR)")
@click.option('-c', '--config', default='config/config.json', envvar='DNSJINJA_CONFIG', show_default=True, help="Konfigurationsdatei (DNSJINJA_CONFIG)")
@click.option('-u', '--upload', is_flag=True, default=False, help="Upload der Zonen")
@click.option('-b', '--backup', is_flag=True, default=False, help="Backup der Zonen")
@click.option('-w', '--write', is_flag=True, default=False, help="Zone-Files schreiben")
@click.option('-C', '--create-missing', is_flag=True, default=False, help="Konfigurierte Domains, die beim Backend nicht existieren, neu anlegen")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN', help="API-Token für das DNS-Backend (DNSJINJA_AUTH_API_TOKEN, oder DNSJINJA_<BACKEND>_AUTH_API_TOKEN)")
@click.option('--dry-run', 'dry_run', is_flag=True, default=False, help="Zone-Files rendern und ausgeben, ohne zu schreiben oder hochzuladen")
@click.option('--dry-run-compare', 'dry_run_compare', is_flag=True, default=False, help="Unterschiede zwischen Live-Daten des Backends und Templates anzeigen, ohne etwas zu ändern")
@click.option('--show-ttl', 'show_ttl', is_flag=True, default=False, help="Bei --dry-run-compare auch reine TTL-Abweichungen auflisten")
def run(upload, backup, write, datadir, config, auth_api_token, create_missing, dry_run, dry_run_compare, show_ttl):
    """Modulare Verwaltung von DNS-Zonen (Backend über config.json wählbar)"""
    if dry_run and dry_run_compare:
        click.echo('--dry-run und --dry-run-compare können nicht kombiniert werden.')
        sys.exit(1)
    if dry_run or dry_run_compare:
        # Trockenlauf: create_missing wird zwingend ignoriert, damit auch mit -C
        # keine Zonen beim Backend angelegt werden.
        if create_missing:
            click.echo('Hinweis: --create-missing wird im Trockenlauf ignoriert.')
        dnsjinja = DNSJinja(False, False, False, datadir, config, auth_api_token, False)
        if dry_run:
            dnsjinja.dry_run()
        else:
            dnsjinja.dry_run_compare(show_ttl)
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
