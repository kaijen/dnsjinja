import click
import json
import requests
from .myloadenv import load_env

DEFAULT_API_BASE = "https://api.hetzner.cloud/v1"


class ExploreHetzner:

    def __init__(self, output, auth_api_token="", api_base=""):
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip('/')
        self.out = { 'domains': {} }
        self.auth_api_token = auth_api_token or input('Hetzner API-Token (Bearer): ')
        self.output = output

    def _api_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth_api_token}",
            "Content-Type": "application/json",
        }

    def explore(self):
        try:
            zones_url = f"{self.api_base}/zones"
            page = 1
            while True:
                response = requests.get(
                    url=zones_url,
                    headers=self._api_headers(),
                    params={"page": page, "per_page": 100},
                )
                if response.status_code == 200:
                    r = response.json()
                    for z in r['zones']:
                        self.out['domains'][z['name']] = {
                            'template': "",
                        }
                    pagination = r.get('meta', {}).get('pagination', {})
                    if page >= pagination.get('last_page', page):
                        break
                    page += 1
                else:
                    print(f'{response.url}: {response.status_code}')
                    break
        except requests.exceptions.RequestException:
            print('HTTP Request failed')

        try:
            print(json.dumps(self.out, indent=2), file=self.output)
        except Exception as e:
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
