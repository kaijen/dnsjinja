# Installation

`dnsjinja` läuft mit einem aktuellen Python (≥ 3.10). Bei der Installation per `pip`
werden alle Abhängigkeiten (Jinja2, hcloud, dnspython, Click, pydantic …) automatisch
mitinstalliert. Nach der Installation stehen drei Kommandos zur Verfügung:
`dnsjinja`, `explore_hetzner` und `exit_on_error`.

## Virtuelle Python-Umgebung (empfohlen)

```bash
python -m venv .venv
```

Aktivierung:

=== "Linux / macOS"

    ```bash
    source .venv/bin/activate
    ```

=== "Windows (PowerShell)"

    ```powershell
    .venv\Scripts\Activate.ps1
    ```

Installation in der aktivierten Umgebung:

=== "HTTPS"

    ```bash
    pip install git+https://github.com/kaijen/dnsjinja.git
    ```

=== "SSH"

    ```bash
    pip install git+ssh://git@github.com/kaijen/dnsjinja.git
    ```

=== "Bestimmte Version (Tag)"

    ```bash
    pip install git+https://github.com/kaijen/dnsjinja.git@v1.0.1
    ```

Eine bestimmte Version per Tag zu installieren ist für reproduzierbare Abläufe
(z. B. in CI) empfehlenswert.

## Umgebungsvariablen

Die wichtigste Variable ist das API-Token. Variablen können direkt gesetzt oder in einer
`.env`-Datei hinterlegt werden. `dnsjinja` lädt `.env`-Dateien in dieser Reihenfolge
(spezifisch vor allgemein, bereits gesetzte Variablen werden nie überschrieben):

1. `<aktuelles Verzeichnis>/dnsjinja.env` und `.env`
2. `$HOME/.dnsjinja/dnsjinja.env` und `.env`
3. plattformspezifisches Config-Verzeichnis (`~/.config/dnsjinja/` unter Linux)
4. `/etc/dnsjinja/` (Linux/macOS)

Am gebräuchlichsten ist `$HOME/.dnsjinja/dnsjinja.env` (siehe
[`samples/dnsjinja.env.sample`](https://github.com/kaijen/dnsjinja/blob/main/samples/dnsjinja.env.sample)):

```bash title="$HOME/.dnsjinja/dnsjinja.env"
DNSJINJA_AUTH_API_TOKEN=dein-hetzner-cloud-token
DNSJINJA_DATADIR=/pfad/zum/daten-repo
DNSJINJA_CONFIG=config/config.json
```

!!! danger "Token sicher ablegen"
    Das API-Token gewährt Schreibzugriff auf deine DNS-Zonen. Lege `.env`-Dateien
    außerhalb der Versionsverwaltung ab (`.gitignore`) und schütze sie mit
    restriktiven Dateirechten.

## Docker

Alternativ lässt sich `dnsjinja` containerisiert ausführen. Das Dockerfile nutzt ein
Multi-Stage-Build mit zwei Targets:

- **`prod`** – Produktions-Container mit installiertem `dnsjinja`
- **`dev`** – Entwicklungs-Container mit `pip install -e .` (editierbar)

### Mit docker compose

Das Daten-Repository wird als Volume eingebunden; `DNSJINJA_DATADIR` zeigt auf dem
Host auf das Daten-Repository:

```bash
DNSJINJA_AUTH_API_TOKEN=<token> DNSJINJA_DATADIR=/pfad/zum/daten-repo \
  docker compose run --rm dnsjinja -b -w -u
```

### Mit docker build/run

```bash
docker build --target prod -t dnsjinja .

docker run --rm \
  -v /pfad/zum/daten-repo:/data \
  -e DNSJINJA_AUTH_API_TOKEN=<token> \
  -e DNSJINJA_DATADIR=/data \
  -e DNSJINJA_CONFIG=/data/config/config.json \
  dnsjinja -b -w -u
```

Da der `ENTRYPOINT` auf `dnsjinja` gesetzt ist, wird `explore_hetzner` über
`--entrypoint` aufgerufen:

```bash
docker compose run --rm --entrypoint explore_hetzner dnsjinja --auth-api-token <token>
```

## Installation prüfen

```bash
dnsjinja --help
```

Wenn die Hilfe erscheint, ist alles bereit für den [Schnellstart](schnellstart.md).
