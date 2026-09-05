"""Liest die vorhandenen Zonen eines DNS-Backends aus und erzeugt daraus ein
Gerüst für die config.json.

Löst frühere Fassung explore_hetzner ab; der alte Kommandoname bleibt als Alias
erhalten.
"""

import getpass
import json
import os
import sys

import click

from .backends import BackendError, UnknownBackendError, available_backends, create_backend
from .myloadenv import load_env


class ExploreDNS:

    def __init__(self, output, backend_name: str = 'hetzner',
                 auth_api_token: str = '', api_base: str = '') -> None:
        self.out: dict[str, dict] = {'domains': {}}
        self.backend_name = backend_name
        self.output = output

        env_specific = f'DNSJINJA_{backend_name.upper().replace("-", "_")}_AUTH_API_TOKEN'
        token = (
            auth_api_token
            or os.environ.get(env_specific, '')
            or os.environ.get('DNSJINJA_AUTH_API_TOKEN', '')
            or getpass.getpass(f'API-Token für {backend_name}: ')
        )
        try:
            self.backend = create_backend(backend_name, token=token, api_base=api_base)
        except UnknownBackendError as e:
            click.echo(str(e), err=True)
            sys.exit(1)

    def explore(self) -> None:
        try:
            for name in sorted(self.backend.list_zones()):
                self.out['domains'][name] = {'template': ''}
        except BackendError as e:
            click.echo(f'Fehler beim Abfragen der Zonen: {e}', err=True)

        if self.backend_name != 'hetzner':
            self.out['global'] = {'dns-backend': self.backend_name}

        try:
            click.echo(json.dumps(self.out, indent=2), file=self.output)
        except OSError as e:
            click.echo(f'Fehler beim Schreiben von {self.output}: {str(e)}', err=True)


@click.command()
@click.option('-o', '--output', type=click.File('w'), default='-',
              help="Ausgabedatei für die Ergebnisse")
@click.option('-B', '--dns-backend', 'dns_backend', default='hetzner',
              envvar='DNSJINJA_DNS_BACKEND', show_default=True,
              help="DNS-Backend (DNSJINJA_DNS_BACKEND)")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN',
              help="API-Token für das DNS-Backend (DNSJINJA_AUTH_API_TOKEN)")
@click.option('--api-base', default="", envvar='DNSJINJA_API_BASE',
              help="Basis-URL der API (DNSJINJA_API_BASE)")
@click.option('--list-backends', is_flag=True, default=False,
              help="Verfügbare DNS-Backends auflisten und beenden")
def run(output, dns_backend, auth_api_token, api_base, list_backends):
    """Vorhandene DNS-Zonen eines Backends auslesen"""
    if list_backends:
        for name, herkunft in available_backends().items():
            click.echo(f'{name} ({herkunft})')
        return
    ex = ExploreDNS(output, dns_backend, auth_api_token, api_base)
    ex.explore()


def main():
    load_env('dnsjinja')
    run()


if __name__ == '__main__':

    # Umgebungsvariablen noch bei Bedarf aus .env laden
    main()
