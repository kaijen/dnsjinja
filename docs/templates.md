# Template-Architektur

Die Templates nutzen eine modulare Include-Architektur mit dynamischer
Provider-Auswahl. Ein einziges Haupt-Template (`standard.tpl`) genügt für alle
Domains – welche Records entstehen, steuert die Konfiguration je Domain.

## Verzeichnisstruktur

```
templates/
├── standard.tpl              # Einstiegspunkt je Domain
└── include/
    ├── 00-ttl.inc            # $ORIGIN + $TTL
    ├── 00-meta.inc           # SOA + NS + Records der Hauptdomain
    ├── 00-subdomain-meta.inc # Provider-Includes + Custom-Records
    ├── soa/                  # SOA-Records je DNS-Provider
    ├── ns/                   # NS-Records je DNS-Provider
    ├── mail/                 # MX, SPF, DKIM, DMARC je Mail-Provider
    ├── www/                  # A/AAAA je Web-Provider
    ├── xmpp/                 # SRV je XMPP-Provider
    ├── custom/               # domain-spezifische Records
    ├── custom-groups/        # gemeinsame Konfigurationen
    └── validation/           # Domain-Validierungs-TXT-Records
```

## Rendering-Ablauf

```
standard.tpl (je Domain)
├── include/00-ttl.inc              → $ORIGIN + $TTL
├── include/00-meta.inc             → SOA + NS + Records der Hauptdomain
│   ├── include/soa/soa_<provider>.inc      (Standard: hetzner)
│   ├── include/ns/ns_<provider>.inc        (Standard: hetzner)
│   └── include/00-subdomain-meta.inc
│       ├── include/mail/mail_<provider>.inc        (optional)
│       ├── include/xmpp/xmpp_<provider>.inc        (optional)
│       ├── include/www/www_<provider>.inc          (optional)
│       ├── include/custom/<domain>.inc             (optional)
│       └── include/custom-groups/<gruppe>.inc      (je Gruppe, optional)
└── für jede Subdomain:
    ├── include/00-ttl.inc          → $ORIGIN für <sub>.<domain>
    └── include/00-subdomain-meta.inc → gleiche Provider-Includes
```

## Dynamische Provider-Auswahl

Include-Dateinamen werden aus den Konfigurationswerten zusammengesetzt:

```jinja2
{% set include_mail = 'include/mail/mail_' + mail|default('none') + '.inc' %}
{% include include_mail ignore missing %}
```

Ist `"mail": "example-provider"` gesetzt, wird `include/mail/mail_example-provider.inc`
eingebunden. Fehlt das Feld `mail`, wird `mail_none.inc` gesucht – existiert die Datei
nicht, sorgt `ignore missing` dafür, dass sie stillschweigend übersprungen wird.

Dasselbe Prinzip gilt für **alle** Kategorien: `mail`, `www`, `xmpp`, `soa` und `ns`.
Für `soa` und `ns` ist der Standardwert `hetzner`.

## Custom-Records, Shared Groups, Validierung

**Domain-spezifisch** – `include/custom/<domain>.inc` wird automatisch eingebunden,
wenn die Datei existiert. Keine Änderung an der Konfiguration nötig.

**Shared Groups** – Konfigurationen für mehrere Domains liegen in
`include/custom-groups/<name>.inc` und werden per `"custom_groups": ["<name>"]`
referenziert.

**Validierung** – Ownership-Nachweise (z. B. für Mail-Provider) liegen in
`include/validation/<domain>.inc` und werden typischerweise aus den Mail-Includes
heraus eingebunden:

```jinja2
{% set include_validation = 'include/validation/' + domain + '.inc' %}
{% include include_validation ignore missing %}
```

## Subdomains

Subdomains werden in einer Schleife verarbeitet. Dabei wird `domain` auf den
vollqualifizierten Namen gesetzt (z. B. `blog.example.com`); es greifen dieselben
Include-Dateien wie für die Hauptdomain:

```jinja2
{% set org_domain = domain %}
{% for dom in subdomains %}
{% set domain = dom + '.' + org_domain %}
{% include 'include/00-subdomain-meta.inc' %}
{% endfor %}
```

Eigene Records für eine Subdomain kommen in `include/custom/<subdomain>.<domain>.inc`
(z. B. `include/custom/blog.example.com.inc`).

## Jinja2-Variablen in Templates

| Variable | Quelle | Beschreibung |
|----------|--------|-------------|
| `domain` | automatisch | aktuell verarbeitete Domain (für Subdomains überschrieben) |
| `soa_serial` | automatisch | SOA-Seriennummer im Format `JJJJMMTT##` |
| `mail` / `www` / `xmpp` | Konfiguration | Provider-Auswahl |
| `registrar` | Konfiguration | Registrar-Name für den TXT-Record am Zonen-Apex |
| `subdomains` | Konfiguration | Liste der Subdomains |
| `custom_groups` | Konfiguration | Liste der Shared Groups |

## Eigener Jinja2-Filter: `hostname`

Der Filter `hostname` löst einen Hostnamen in eine IPv4-Adresse auf – nützlich, um
einen A-Record an einen externen Namen zu binden:

```jinja2
server  IN  A  {{ "mail.example.com" | hostname }}
```

## Wichtig: Namen und Werte

Hetzners RRSet-API ist strenger als das klassische Zonefile-Import:

!!! warning "Konventionen für gültige Records"
    - **Owner-Namen kleinschreiben.** Großbuchstaben im Record-Namen (z. B.
      `Selector1._domainkey`) werden abgelehnt. `@` ist als Owner-Name erlaubt.
    - **Werte als FQDN mit Punkt** schreiben, wenn auf den Zonen-Apex oder externe
      Ziele verwiesen wird (`name IN CNAME example.com.`, nicht `@`).
    - **Lange TXT-Records** (z. B. DKIM-Schlüssel) gehören in **eine** Zeile bzw. in
      korrekt zusammengesetzte ≤255-Zeichen-Strings – ein Zeilenumbruch innerhalb der
      Anführungszeichen ist ungültig.

    `dnsjinja` validiert jedes gerenderte Zone-File vor dem Upload mit
    [dnspython](https://www.dnspython.org/); Syntaxfehler brechen den Lauf ab.

## Neuen Provider hinzufügen

1. Include-Datei anlegen: `include/<kategorie>/<kategorie>_<name>.inc`
   (z. B. `include/mail/mail_neuer-provider.inc`).
2. In der Domain-Konfiguration referenzieren: `"mail": "neuer-provider"`.

Mehr ist nicht nötig – das Haupt-Template bleibt unverändert.
