# Automatisierung mit GitHub Actions

`dnsjinja` lässt sich vollständig über GitHub Actions betreiben: Ein Workflow im
**Daten-Repository** spielt bei jedem Push auf `main` die DNS-Zonen aus.

## Ablauf

1. `dnsjinja` wird (versions-gepinnt) aus dem Tool-Repository installiert.
2. Das Daten-Repository wird ausgecheckt.
3. `dnsjinja -b -w -u` wird ausgeführt (Backup, Write, Upload).
4. Zone-Files und Backups werden als Build-Artefakte gesichert.
5. `exit_on_error` setzt den Job auf „failure", falls eine Domain nicht
   aktualisiert werden konnte.

## Secrets und Variables

Im Daten-Repository unter **Settings → Secrets and variables → Actions**:

| Name | Typ | Inhalt |
|------|-----|--------|
| `HETZNER_API_AUTH_TOKEN` | Secret | Bearer-Token (Cloud API, Read & Write) |
| `GH_PAT_DNSJINJA` | Secret | GitHub-PAT mit Lesezugriff auf das (private) `dnsjinja`-Repo |
| `DNSJINJA` | Variable | Repo-Pfad des Tools, z. B. `kaijen/dnsjinja` |
| `DNSDATA` | Variable | Repo-Pfad der DNS-Daten |
| `DNSJINJA_VER` | Variable | zu installierender Tag, z. B. `v1.0.1` |

!!! warning "Token-Typ"
    `HETZNER_API_AUTH_TOKEN` muss ein **Cloud-API-Token** sein (nicht der alte
    DNS-Konsolen-Token), sonst scheitert der Lauf an der Authentifizierung.

## Beispiel-Workflow

`.github/workflows/publish_dns.yml` im Daten-Repository:

```yaml
name: Publish DNS to Hetzner

on:
  push:
    branches: [main]

env:
  DNSJINJA_AUTH_API_TOKEN: ${{ secrets.HETZNER_API_AUTH_TOKEN }}
  DNSJINJA_DATADIR: data
  DNSJINJA_CONFIG: data/config/config.json

jobs:
  dns-hetzner:
    runs-on: ubuntu-latest
    steps:
      - name: Install dnsjinja
        run: pip install git+https://${{ secrets.GH_PAT_DNSJINJA }}@github.com/${{ vars.DNSJINJA }}.git@${{ vars.DNSJINJA_VER }}

      - name: Check out DNS data
        uses: actions/checkout@v4
        with:
          repository: ${{ vars.DNSDATA }}
          path: ${{ env.DNSJINJA_DATADIR }}

      - name: Run dnsjinja
        run: |
          mkdir ${{ env.DNSJINJA_DATADIR }}/zone-files
          mkdir ${{ env.DNSJINJA_DATADIR }}/zone-backups
          dnsjinja -b -w -u

      - name: Upload Zone Backups
        uses: actions/upload-artifact@v4
        with:
          name: zone-backups
          path: ${{ env.DNSJINJA_DATADIR }}/zone-backups

      - name: Upload Zone Files
        uses: actions/upload-artifact@v4
        with:
          name: zone-files
          path: ${{ env.DNSJINJA_DATADIR }}/zone-files

      - name: Set error status
        run: exit_on_error
```

!!! tip "Version pinnen"
    `@${{ vars.DNSJINJA_VER }}` installiert einen festen Tag statt des Default-Branches.
    Updates erfolgen dann kontrolliert durch Hochsetzen der Variable `DNSJINJA_VER` –
    reproduzierbar und nachvollziehbar.

## Diese Dokumentation: Versionierung mit mike

Die Doku selbst wird mit [MkDocs](https://www.mkdocs.org/) erstellt und mit
[mike](https://github.com/jimporter/mike) je Release versioniert. Ein Workflow im
`dnsjinja`-Repo baut die Seiten bei jedem **Tag-Push (`v*`)** und veröffentlicht sie in
den Branch `gh-pages`:

```yaml
name: Publish Docs

on:
  push:
    tags: ['v*']
  workflow_dispatch:
    inputs:
      version:
        description: 'Version/Alias (z. B. v1.0.1)'
        required: true

permissions:
  contents: write

jobs:
  deploy-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install ".[docs]"
      - name: Configure git
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      - name: Deploy with mike
        run: |
          VERSION="${{ github.event.inputs.version || github.ref_name }}"
          git fetch origin gh-pages --depth=1 || true
          mike deploy --push --update-aliases "$VERSION" latest
          mike set-default --push latest
```

`mike` legt jede Version in einen eigenen Unterpfad (`/v1.0.1/`) und pflegt den Alias
`latest`. Der Versionsumschalter oben rechts wird vom Material-Theme automatisch
eingeblendet.

!!! note "Eigener Webserver statt GitHub Pages"
    Der Workflow schreibt ausschließlich in den Branch `gh-pages`. Du musst GitHub
    Pages **nicht** aktivieren – der Branch enthält eine fertige, statische Site, die
    du auf deinem eigenen Webserver ausliefern kannst (z. B. per Checkout/Export des
    Branches). Passe dazu `site_url` in `mkdocs.yml` an deine tatsächliche URL an,
    damit kanonische Links und `sitemap.xml` stimmen.

### Lokale Vorschau

```bash
pip install ".[docs]"

# Live-Vorschau ohne Versionierung
mkdocs serve

# Versioniert wie in Produktion (lokal)
mike deploy 1.0.1 latest
mike set-default latest
mike serve
```
