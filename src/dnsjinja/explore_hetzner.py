import click
import getpass
import json
import hcloud
from hcloud import Client
from .myloadenv import load_env

DEFAULT_API_BASE = "https://api.hetzner.cloud/v1"


class ExploreHetzner:

    def __init__(self, output, auth_api_token="", api_base=""):
        self.out = { 'domains': {} }
        auth_api_token = auth_api_token or getpass.getpass('Hetzner API-Token (Bearer): ')
        api_base = (api_base or DEFAULT_API_BASE).rstrip('/')
        self.client = Client(token=auth_api_token, api_endpoint=api_base)
        self.output = output

    def explore(self):
        try:
            all_zones = self.client.zones.get_all()
            for z in all_zones:
                self.out['domains'][z.name] = {
                    'template': "",
                }
        except hcloud.APIException as e:
            print(f'Fehler beim Abfragen der Zonen: {e}')

        try:
            print(json.dumps(self.out, indent=2), file=self.output)
        except OSError as e:
            print(f'Fehler beim Schreiben von {self.output}: {str(e)}')


@click.command()
@click.option('-o', '--output', type=click.File('w'), default='-', help="Ausgabedatei für die Ergebnisse")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN', help="API-Token (Bearer) für Hetzner Cloud API (DNSJINJA_AUTH_API_TOKEN)")
@click.option('--api-base', default="", envvar='DNSJINJA_API_BASE', help="Basis-URL der Hetzner Cloud API (DNSJINJA_API_BASE)")
def run(output, auth_api_token, api_base):
    """Explore Hetzner DNS Zones (Cloud API)"""
    ex = ExploreHetzner(output, auth_api_token, api_base)
    ex.explore()


def main():
    load_env('dnsjinja')
    run()


if __name__ == '__main__':

    # Umgebungsvariablen noch bei Bedarf aus .env laden
    main()
