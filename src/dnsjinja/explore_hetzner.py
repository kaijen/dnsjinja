import click
import json
import requests
# from rich import print
from .myloadenv import load_env


class ExploreHetzner:

    def __init__(self, output, auth_api_token=""):
        self.zones_api_url = "https://dns.hetzner.com/api/v1/zones"
        self.out = { 'domains': {} }
        self.auth_api_token = auth_api_token or input('Hetzner AUTH-API-TOKEN: ')
        self.output = output

    def explore(self):
        try:
            response = requests.get(
                url=self.zones_api_url,
                headers={
                    "Auth-API-Token": self.auth_api_token,
                },
            )
            if response.status_code == 200:
                r = response.json()
                for z in r['zones']:
                    self.out['domains'][z['name']] = {
                        'zone-id': z['id'],
                        'template': "",
                        'zone-file': ""
                    }
            else:
                print(f'{response.url}: {response.status_code}')
        except requests.exceptions.RequestException:
            print('HTTP Request failed')

        try:
            print(json.dumps(self.out,indent=2), file=self.output)
        except Exception as e:
            print(f'Fehler beim Schreiben von {self.output}: {str(e)}')


@click.command()
@click.option('-o', '--output', type=click.File('w'), default='-', help="Ausgabedatei für die Ergebnisse")
@click.option('--auth-api-token', default="", envvar='DNSJINJA_AUTH_API_TOKEN', help="AUTH-API-TOKEN für REST-API (DNSJINJA_AUTH_API_TOKEN)")
def run(output, auth_api_token):
    """Expore Hetzner DNS Zones"""
    ex = ExploreHetzner(output, auth_api_token)
    ex.explore()


def main():
    load_env('dnsjinja')
    run()


if __name__ == '__main__':

    # Umgebungsvariablen noch bei Bedarf aus .env laden
    main()
