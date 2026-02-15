# DNSJinja – Code Review & Verbesserungsvorschläge

Stand: 2026-02-15
Grundlage: Quellcode-Analyse aller Dateien unter `src/dnsjinja/` und `tests/`

---

## Legende

| Schweregrad | Bedeutung |
|-------------|-----------|
| 🔴 Hoch     | Sicherheitsproblem oder reproduzierbarer Bug mit Datenverlust-Potential |
| 🟠 Mittel   | Bug oder sicherheitsrelevantes Design-Problem |
| 🟡 Niedrig  | Code-Qualität, Wartbarkeit, Best Practice |
| 🔵 Idee     | Feature-Vorschlag, kein dringender Handlungsbedarf |

---

## 5 – Sicherheit & Kritische Bugs (Drittes Review)

### 5.1 🔴 SSRF-Risiko: `gethostbyname` als Jinja2-Filter (`dnsjinja.py:135`)

Der Filter `hostname` wird als `gethostbyname` aus dem Standard-Socket-Modul
registriert:

```python
self.env.filters['hostname'] = gethostbyname
```

Ein Template-Autor kann damit beliebige Hostnamen auflösen – einschließlich
interner Netzwerkadressen (`169.254.0.0/16`, `10.0.0.0/8`, `127.0.0.1`). Da
`gethostbyname` eine vollständige DNS-Auflösung über das Betriebssystem
durchführt, entsteht ein Server-Side-Request-Forgery-Risiko (SSRF), sobald
Templates aus nicht vertrauenswürdigen Quellen stammen.

Zusätzlich wird eine nicht gesandbüchste `jinja2.Environment` verwendet. Ein
Angreifer mit Schreibzugriff auf Template-Dateien kann über `__class__`,
`__mro__` und `__subclasses__` beliebigen Python-Code ausführen (Jinja2
Template Injection).

**Empfehlung:**

1. `jinja2.sandbox.SandboxedEnvironment` statt `Environment` verwenden.
2. Den `hostname`-Filter entfernen oder durch eine Allowlist-geprüfte Variante
   ersetzen, die nur öffentliche IP-Adressen zurückgibt.

```python
# vorher:
from jinja2 import Environment, FileSystemLoader
...
self.env = Environment(
    loader=FileSystemLoader(self.templates_dir), ...)
self.env.filters['hostname'] = gethostbyname

# nachher:
from jinja2.sandbox import SandboxedEnvironment
...
self.env = SandboxedEnvironment(
    loader=FileSystemLoader(self.templates_dir), ...)
# hostname-Filter weglassen oder sicher reimplementieren
```

---

### 5.2 🔴 SOA-Serial-Format wird nicht validiert (`dnsjinja.py:152–163`)

`_new_zone_serial()` geht davon aus, dass der aktuelle SOA-Serial exakt im
Format `YYYYMMDDNN` (10 Ziffern) vorliegt:

```python
soa_serial = self._get_zone_serial(domain)
serial_prefix = soa_serial[:-2]          # erwartet 8 Zeichen YYYYMMDD
if self.today == serial_prefix:
    suffix_int = int(soa_serial[-2:]) + 1  # erwartet 2-stellige Zahl
```

Wenn der bisherige Serial kein YYYYMMDDNN-Serial ist (z.B. ein Unix-Timestamp
wie `1700000000` oder ein manuell gesetzter Wert), dann:

- `soa_serial[:-2]` liefert falsche 8 Zeichen → `self.today == serial_prefix`
  wird nie wahr → `serial_suffix = '01'` ist harmlos, aber
- `int(soa_serial[-2:])` kann bei nicht-numerischen Suffixen (z.B. `'00'` vs.
  einem anderen Format) zu einem unerwarteten `ValueError` führen, der nicht
  abgefangen wird.
- Serials mit weniger als 10 Zeichen führen zu einem 9-stelligen oder kürzeren
  neuen Serial, der DNS-ungültig ist.

**Empfehlung:** Serial-Format vor der Weiterverarbeitung validieren:

```python
import re

_SOA_SERIAL_RE = re.compile(r'^\d{10}$')

def _new_zone_serial(self, domain: str) -> str:
    soa_serial = self._get_zone_serial(domain)
    if not _SOA_SERIAL_RE.fullmatch(soa_serial):
        click.echo(
            f'SOA-Serial für {domain} hat unerwartetes Format: '
            f'{soa_serial!r} – wird als veraltet behandelt.'
        )
        return self.today + '01'
    serial_prefix = soa_serial[:-2]
    ...
```

---

### 5.3 🔴 Pointer-Datei `/tmp/dnsjinja.exit.ptr` ist race-condition-anfällig (`dnsjinja.py:92–94`, `exit_on_error.py:6,18–19`)

Die Pointer-Datei hat einen festen, vorhersagbaren Namen im systemweiten
`/tmp`-Verzeichnis:

```python
# dnsjinja.py
(Path(tempfile.gettempdir()) / "dnsjinja.exit.ptr").write_text(
    str(self.exit_status_file), encoding='utf-8'
)
```

```python
# exit_on_error.py
_POINTER_FILE = Path(tempfile.gettempdir()) / "dnsjinja.exit.ptr"
```

Ein lokaler Angreifer kann vor dem Prozessstart einen Symlink
`/tmp/dnsjinja.exit.ptr → /etc/passwd` anlegen. `write_text()` würde dann
in `/etc/passwd` schreiben (sofern der Prozess ausreichende Rechte hat) oder
der Inhalt der Pointer-Datei wird durch einen anderen Prozess auf eine
beliebige Datei umgelenkt.

Bei parallelen Läufen überschreiben sich Prozesse gegenseitig die
Pointer-Datei, sodass `exit_on_error` den falschen Exit-Code liest.

**Empfehlung:**

1. Pointer-Datei ebenfalls mit PID parametrisieren:
   `dnsjinja.{pid}.exit.ptr`
2. Alternativ: Exit-Code-Datei-Pfad ausschließlich via
   `DNSJINJA_EXIT_FILE` übergeben und auf die Pointer-Datei ganz
   verzichten.
3. Vor `write_text()` sicherstellen, dass kein Symlink existiert
   (`not path.is_symlink()`).

---

## 6 – Bugs & Design-Probleme (Drittes Review)

### 6.1 🟠 `DomainConfigEntry` TypedDict nie zur Laufzeit genutzt (`dnsjinja.py:27–31`)

Das TypedDict `DomainConfigEntry` ist definiert, wird aber nirgendswo im Code
als Typ-Annotation verwendet. `self.config['domains']` ist ein rohes
`dict[str, Any]` (geladen via `json.load()`). PyTypeChecker und mypy wissen
nichts von der TypedDict-Annotation, weil der Dict-Wert nicht gecastet wird.

```python
# Aktuell: DomainConfigEntry wird nicht genutzt
self.config['domains'][d]['zone-id'] = hetzner_zones[d].id  # untyped
```

**Empfehlung:** Entweder konsequent verwenden:

```python
domains: dict[str, DomainConfigEntry] = self.config['domains']  # type: ignore[assignment]
```

oder den TypedDict entfernen und durch reine Kommentare ersetzen bis eine
vollständige Typisierung der Config-Ladelogik umgesetzt wird.

---

### 6.2 🟠 Nicht-deterministische Ausgabe bei Hetzner-Domains ohne Config (`dnsjinja.py:72–73`)

Die Iteration über `hetzner_zones.keys() - config_domains` liefert eine
Set-Differenz, deren Reihenfolge in Python nicht definiert ist:

```python
for d in (hetzner_zones.keys() - config_domains):
    click.echo(f'{d} ist bei Hetzner eingerichtet aber nicht konfiguriert - bitte prüfen')
```

In Logs und CI-Ausgaben erscheinen die Domains in zufälliger Reihenfolge,
was Diffs unleserlich macht.

**Empfehlung:** `sorted()` analog zur Behandlung der Gegenmenge verwenden:

```python
for d in sorted(hetzner_zones.keys() - config_domains):
    click.echo(...)
```

---

### 6.3 🟠 `jinja2.Environment` nicht gesandkastet (`dnsjinja.py:130–134`)

Auch ohne den `hostname`-Filter (Punkt 5.1) ist `jinja2.Environment` nicht
gesandkastet. Template-Dateien haben Zugriff auf Python-Interna und könnten
bei Schreibzugriff auf `templates/` beliebigen Code ausführen.

**Empfehlung:** `jinja2.sandbox.SandboxedEnvironment` verwenden (siehe 5.1).

---

### 6.4 🟠 `backup_zone()` fragt SOA-Serial redundant ab (`dnsjinja.py:220`)

```python
backupfile = self.zone_backups_dir / Path(
    self.config['domains'][domain]['zone-file'] + f'.{self._get_zone_serial(domain)}'
)
```

`_get_zone_serial()` löst eine DNS-SOA-Abfrage aus. Der gleiche Serial wurde
bereits bei `_create_zone_data()` berechnet und in `self._serials[domain]`
gecacht. Der Backup-Dateiname sollte den bereits bekannten Serial verwenden:

```python
# nachher:
backupfile = self.zone_backups_dir / Path(
    self.config['domains'][domain]['zone-file'] + f'.{self._serials[domain]}'
)
```

Das eliminiert eine unnötige DNS-Abfrage pro Domain und stellt sicher, dass
der Backup-Dateiname mit dem hochgeladenen Serial übereinstimmt.

---

### 6.5 🟠 `upload_zones()` maskiert `UploadError` mit `OSError` (`dnsjinja.py:206–214`, `dnsjinja.py:182–187`)

`write_zone_files()` und `upload_zones()` werden in `run()` sequenziell
aufgerufen. Ein `OSError` in `write_zone_files()` wird dort zwar mit
`click.echo` ausgegeben, aber nicht weitergeworfen – Ausführung geht weiter.
In `upload_zones()` werden `UploadError`-Exceptions gefangen und per
`continue` übersprungen. Wenn ein Upload-Fehler auftritt und danach
`backup_zones()` durchläuft, wird `exit_status_file` mit `254` beschrieben,
aber ein davor aufgetretener `OSError` beim Schreiben bleibt im Exit-Code
unsichtbar.

**Empfehlung:** Fehlerzähler einführen und am Ende mit angepasstem Exit-Code
abschließen:

```python
errors = 0
for domain in self.config["domains"]:
    try:
        self.upload_zone(domain)
    except UploadError as e:
        click.echo(f'Domäne {domain} konnte nicht aktualisiert werden: {e}')
        errors += 1
if errors:
    self.exit_status_file.write_text(str(errors), encoding='utf-8')
```

---

### 6.6 🟠 Pydantic `extra='allow'` schwächt Schema-Validierung (`dnsjinja_config_schema.py:6,12,26`)

Alle drei Pydantic-Modelle erlauben beliebige Zusatzfelder:

```python
model_config = ConfigDict(extra='allow', populate_by_name=True)
```

Tippfehler in `config.json` (z.B. `"zone-file"` statt `"zone-files"`) werden
stillschweigend ignoriert statt als Validierungsfehler gemeldet.

**Empfehlung:** `extra='forbid'` für `GlobalConfig` verwenden:

```python
class GlobalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
```

`DomainConfig` und `DnsJinjaConfig` können `extra='allow'` behalten, da
Domain-Einträge beliebige Template-Variablen enthalten dürfen.

---

### 6.7 🟠 Leere `name-servers`-Liste in Pydantic nicht abgefangen (`dnsjinja_config_schema.py:16`)

```python
name_servers: list[str] = Field(alias='name-servers')
```

Pydantic akzeptiert `"name-servers": []`, was zu einem unklaren Fehler
in `dns.resolver` führt statt zu einer verständlichen Fehlermeldung.

**Empfehlung:** `min_length=1` ergänzen:

```python
name_servers: list[str] = Field(alias='name-servers', min_length=1)
```

---

### 6.8 🟠 `explore_hetzner.py`: API-Fehler wird ignoriert, leeres JSON trotzdem geschrieben (`explore_hetzner.py:21–33`)

```python
def explore(self):
    try:
        all_zones = self.client.zones.get_all()
        ...
    except hcloud.APIException as e:
        click.echo(f'Fehler beim Abfragen der Zonen: {e}', err=True)
    # ← kein return/raise: Ausführung läuft weiter

    try:
        click.echo(json.dumps(self.out, indent=2), file=self.output)
    ...
```

Bei einem API-Fehler wird `self.out` nie befüllt und trotzdem
`{"domains": {}}` als leeres JSON ausgegeben. Der Aufrufer kann nicht
unterscheiden, ob wirklich keine Domains existieren oder ob ein Fehler
vorlag.

**Empfehlung:** Nach dem API-Fehler `return` oder `sys.exit(1)`:

```python
except hcloud.APIException as e:
    click.echo(f'Fehler beim Abfragen der Zonen: {e}', err=True)
    return
```

---

### 6.9 🟠 `_validate_zone_syntax()` fängt nackte `Exception` (`dnsjinja.py:192`)

```python
except (dns.zone.UnknownOrigin, dns.exception.DNSException, Exception) as e:
```

`Exception` überdeckt die spezifischeren Typen vollständig. Jede Ausnahme –
auch `MemoryError`, `RecursionError` und Programmierfehler – wird als
"Syntaxfehler im Zone-File" ausgegeben und führt zu `sys.exit(1)`.

**Empfehlung:** Nackte `Exception` entfernen, da `dns.exception.DNSException`
bereits alle dnspython-Fehler abdeckt:

```python
except (dns.zone.UnknownOrigin, dns.exception.DNSException) as e:
    click.echo(f'Syntaxfehler im Zone-File für {domain}: {e}')
    sys.exit(1)
```

---

### 6.10 🟠 `logging`-Infrastruktur eingerichtet aber nie genutzt (`dnsjinja.py:22`, `dnsjinja.py:261–263`)

`logger = logging.getLogger(__name__)` ist deklariert und `basicConfig` wird
in `main()` konfiguriert, aber `logger.debug()`, `logger.info()`,
`logger.warning()` werden nirgends aufgerufen. Die Infrastruktur ist
wirkungslos.

**Empfehlung:** Entweder `logger`-Aufrufe einführen (z.B. für Debug-Ausgaben)
oder den Logger vorerst entfernen bis er tatsächlich verwendet wird.
Kandidaten für `logger.debug()`:

```python
logger.debug('Lade Konfiguration aus %s', self.config_file)
logger.debug('Zone %s hat Serial %s', domain, soa_serial)
logger.debug('Lade Template %s für %s', template_name, domain)
```

---

## 7 – Code-Qualität (Drittes Review)

### 7.1 🟡 `today`-Property ohne Mehrwert (`dnsjinja.py:139–141`)

```python
@property
def today(self) -> str:
    return self._today
```

Die Property macht `_today` nach außen sichtbar, ohne Validierungslogik
hinzuzufügen. Weder intern noch in Tests wird `dnsjinja.today` verwendet
(nur `self.today` intern). Die Property ist toter Code.

**Empfehlung:** Property entfernen und überall direkt `self._today` verwenden,
oder das Attribut in `today` (ohne Unterstrich) umbenennen wenn externe
Lesbarkeit gewünscht ist.

---

### 7.2 🟡 `# noinspection PyTypeChecker`-Kommentare ohne Typ-Cast (`dnsjinja.py:104–109`)

```python
# noinspection PyTypeChecker
self.templates_dir = DNSJinja._check_path(self.config['global']['templates'], ...)
```

Der Kommentar unterdrückt eine IDE-Warnung, statt den Wurzelgrund zu
beheben. `self.config['global']['templates']` ist `Any` aus `json.load()`,
und `_check_path` erwartet `str`. Ein expliziter Cast ist lesbarer:

```python
self.templates_dir = DNSJinja._check_path(
    str(self.config['global']['templates']), self.datadir, 'Template-Verzeichnis', expect='dir'
)
```

Alternativ: nach `_DnsJinjaConfigModel.model_validate()` das Pydantic-Objekt
für Zugriff nutzen.

---

### 7.3 🟡 Redundanter Import `from hcloud import Client` (`dnsjinja.py:6–7`)

```python
import hcloud
from hcloud import Client
```

`Client` wird als `Client(token=..., api_endpoint=...)` aufgerufen
(`dnsjinja.py:116`). Da `hcloud` bereits importiert ist, kann
`hcloud.Client(...)` verwendet werden, womit `from hcloud import Client`
entfällt:

```python
import hcloud
# kein from hcloud import Client mehr nötig
...
self.client = hcloud.Client(token=self.auth_api_token, api_endpoint=self._api_base)
```

Gleiches gilt für `explore_hetzner.py:4–5`.

---

### 7.4 🟡 `_check_path` mit String-Parameter `expect` statt `Literal` (`dnsjinja.py:43`)

```python
@staticmethod
def _check_path(path: str, basedir: str, typ: str, expect: str = 'dir') -> Path:
```

`expect` kann beliebige Strings annehmen; ungültige Werte wie `'file '`
(Leerzeichen) würden lautlos als `'dir'` behandelt, weil `if expect == 'dir'`
False wird und `p.is_file()` evaluiert wird. Die Semantik ist fragil.

**Empfehlung:** `Literal` verwenden:

```python
from typing import Literal
@staticmethod
def _check_path(path: str, basedir: str, typ: str,
                expect: Literal['dir', 'file'] = 'dir') -> Path:
```

---

### 7.5 🟡 `**d` in `template.render()` übergibt interne Schlüssel (`dnsjinja.py:175`)

```python
zones[domain] = template.render(domain=domain, soa_serial=soa_serial, **d)
```

`d` enthält nach `_prepare_zones()` auch die internen Schlüssel
`'zone-id'` und `'zone-file'`. Diese werden als Template-Variablen
übergeben. Jinja2 erlaubt keine Bindestrich-Variablen in normaler
Syntax (`{{ zone-id }}` wird als Subtraktion interpretiert), aber durch
`{{ config['zone-id'] }}` oder andere Zugriffsmuster könnten interne
Felder versehentlich in Templates landen und den Zonefile-Inhalt
korrumpieren.

**Empfehlung:** Interne Schlüssel explizit herausfiltern:

```python
template_vars = {k: v for k, v in d.items()
                 if k not in ('zone-id', 'zone-file', 'template')}
zones[domain] = template.render(
    domain=domain, soa_serial=soa_serial, **template_vars
)
```

---

### 7.6 🟡 `ExploreHetzner.__init__` ohne Typ-Annotationen (`explore_hetzner.py:13`)

```python
def __init__(self, output, auth_api_token="", api_base=""):
```

Keine Typ-Annotationen vorhanden. `output` ist ein `click.File`-Objekt
(schreibbares `IO[str]`).

**Empfehlung:**

```python
from typing import IO
def __init__(self, output: IO[str], auth_api_token: str = "", api_base: str = "") -> None:
```

---

### 7.7 🟡 `explore_hetzner.py` nutzt `load_env('dnsjinja')` mit festem Modulnamen (`explore_hetzner.py:47`)

```python
def main():
    load_env('dnsjinja')
    run()
```

`dnsjinja.py` nutzt `load_env()` ohne Parameter (ermittelt Modulnamen
automatisch aus `sys.argv[0]`). In `explore_hetzner.py` ist der Name fest
codiert. Wenn das Skript umbenannt wird, muss auch dieser String geändert
werden.

**Empfehlung:** Konsistenz durch parameterfreien Aufruf:

```python
def main():
    load_env()
    run()
```

---

### 7.8 🟡 Fehlende Tests für `_validate_zone_syntax`, `dry_run`, `_check_path` (`tests/test_unit.py`)

Die folgenden Methoden sind nicht durch Unit-Tests abgedeckt:

- `_validate_zone_syntax()` – kein Test für gültiges/ungültiges Zone-File
- `dry_run()` – kein Test für stdout-Ausgabe
- `_check_path()` – kein Test für fehlende Verzeichnisse/Dateien

**Empfehlung:** Mindestens je einen Positiv- und Negativtest ergänzen.
Beispiel für `_validate_zone_syntax`:

```python
def test_validate_zone_syntax_ungueltig(self, tmp_path, ...):
    # zone mit Syntaxfehler in self.zones[domain] einfügen
    dnsjinja_obj.zones[domain] = "UNGUELTIG"
    with pytest.raises(SystemExit) as exc:
        dnsjinja_obj._validate_zone_syntax(domain)
    assert exc.value.code == 1
```

---

### 7.9 🟡 `pytest-cov` fehlt in `[project.optional-dependencies]` (`pyproject.toml:28–29`)

```toml
[project.optional-dependencies]
test = ["pytest"]
```

`pytest-cov` wird nicht als Abhängigkeit deklariert, ist aber für
Coverage-Reports bei CI/CD notwendig.

**Empfehlung:**

```toml
test = ["pytest", "pytest-cov"]
```

---

### 7.10 🟡 `sys.tracebacklimit = 0` nur im `__main__`-Block (`dnsjinja.py:271`)

```python
if __name__ == '__main__':
    sys.tracebacklimit = 0
    main()
```

Das Setzen von `tracebacklimit = 0` gilt nur wenn das Skript direkt
ausgeführt wird (`python dnsjinja.py`), nicht wenn es via Entry-Point
(`dnsjinja`) oder `python -m dnsjinja` aufgerufen wird. Im normalen
Betrieb erscheinen vollständige Tracebacks bei unbehandelten Ausnahmen.

**Empfehlung:** `tracebacklimit` in `main()` setzen (oder ganz weglassen
und stattdessen alle Ausnahmen explizit abfangen):

```python
def main():
    sys.tracebacklimit = 0
    logging.basicConfig(...)
    load_env()
    run()
```

---

### 7.11 🟡 `__version__` statisch in `__init__.py` statt aus `pyproject.toml` (`__init__.py:5`)

```python
__version__ = '0.3.0'
```

Die Versionsnummer ist an zwei Stellen definiert: `pyproject.toml` und
`__init__.py`. Bei einem Release-Bump muss sie manuell synchronisiert werden.

**Empfehlung:** `importlib.metadata` nutzen:

```python
from importlib.metadata import version, PackageNotFoundError
try:
    __version__ = version('dnsjinja-kaijen')
except PackageNotFoundError:
    __version__ = 'unknown'
```

---

## 8 – Ideen & Erweiterungen (Drittes Review)

### 8.1 🔵 Statische Code-Analyse mit `ruff` konfigurieren

`ruff` als schneller Linter und Formatter ist Standard in modernen
Python-Projekten. Konfiguration in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]
ignore = ["E501"]
```

---

### 8.2 🔵 Typ-Prüfung mit `mypy` konfigurieren

```toml
[tool.mypy]
python_version = "3.10"
strict = false
warn_return_any = true
warn_unused_ignores = true
```

Ergänzung in `[project.optional-dependencies]`:

```toml
dev = ["mypy", "ruff"]
```

---

### 8.3 🔵 `typing.Required` benötigt Python ≥ 3.11 (`dnsjinja.py:5,29`)

```python
from typing import Any, Required, TypedDict
```

`Required` ist seit Python 3.11 in `typing` verfügbar. Mit
`requires-python = ">=3.10"` in `pyproject.toml` schlägt der Import auf
Python 3.10 fehl.

**Empfehlung:** Für Python 3.10-Kompatibilität:

```python
try:
    from typing import Required
except ImportError:
    from typing_extensions import Required
```

Oder `requires-python = ">=3.11"` in `pyproject.toml` setzen und
`typing_extensions` als Abhängigkeit entfernen.

---

### 8.4 🔵 `--create-missing` interaktiv bestätigen lassen

Das Flag `--create-missing` legt Domains bei Hetzner an, ohne eine
Sicherheitsabfrage zu stellen. Bei Tippfehlern in `config.json` könnten
unbeabsichtigt Zones angelegt werden.

**Empfehlung:** Bestätigung vor dem Anlegen einfordern (oder `--yes`-Flag
für nicht-interaktiven Betrieb):

```python
if not yes:
    click.confirm(f'Domain {d} anlegen?', abort=True)
response = self.client.zones.create(name=d, mode="primary")
```

---

## Zusammenfassung (Drittes Review)

| ID   | Schweregrad | Datei                        | Beschreibung                                         |
|------|-------------|------------------------------|------------------------------------------------------|
| 5.1  | 🔴 Hoch     | `dnsjinja.py:135`            | SSRF + Template Injection via `gethostbyname`-Filter |
| 5.2  | 🔴 Hoch     | `dnsjinja.py:152–163`        | SOA-Serial-Format nicht validiert                    |
| 5.3  | 🔴 Hoch     | `dnsjinja.py:92`, `exit_on_error.py:6` | Pointer-Datei race-condition-anfällig    |
| 6.1  | 🟠 Mittel   | `dnsjinja.py:27–31`          | `DomainConfigEntry` TypedDict nie genutzt            |
| 6.2  | 🟠 Mittel   | `dnsjinja.py:72–73`          | Nicht-deterministische Domain-Ausgabe                |
| 6.3  | 🟠 Mittel   | `dnsjinja.py:130–134`        | Unsandkastete Jinja2-Environment                     |
| 6.4  | 🟠 Mittel   | `dnsjinja.py:220`            | Redundante DNS-Abfrage in `backup_zone()`            |
| 6.5  | 🟠 Mittel   | `dnsjinja.py:206–214`        | Fehlerzähler fehlt in `upload_zones()`               |
| 6.6  | 🟠 Mittel   | `dnsjinja_config_schema.py`  | `extra='allow'` maskiert Tippfehler in Config        |
| 6.7  | 🟠 Mittel   | `dnsjinja_config_schema.py:16` | Leere `name-servers`-Liste nicht abgefangen        |
| 6.8  | 🟠 Mittel   | `explore_hetzner.py:21–33`   | API-Fehler → leeres JSON trotzdem ausgegeben         |
| 6.9  | 🟠 Mittel   | `dnsjinja.py:192`            | Nackte `Exception` in `_validate_zone_syntax()`      |
| 6.10 | 🟠 Mittel   | `dnsjinja.py:22,261`         | `logging` eingerichtet aber nie verwendet            |
| 7.1  | 🟡 Niedrig  | `dnsjinja.py:139–141`        | `today`-Property ohne Mehrwert                       |
| 7.2  | 🟡 Niedrig  | `dnsjinja.py:104–109`        | `# noinspection`-Kommentare statt Typ-Cast           |
| 7.3  | 🟡 Niedrig  | `dnsjinja.py:6–7`            | Redundanter `from hcloud import Client`-Import       |
| 7.4  | 🟡 Niedrig  | `dnsjinja.py:43`             | `expect: str` statt `Literal['dir', 'file']`         |
| 7.5  | 🟡 Niedrig  | `dnsjinja.py:175`            | `**d` übergibt interne Schlüssel ans Template        |
| 7.6  | 🟡 Niedrig  | `explore_hetzner.py:13`      | `__init__` ohne Typ-Annotationen                     |
| 7.7  | 🟡 Niedrig  | `explore_hetzner.py:47`      | Fester Modulname `'dnsjinja'` in `load_env()`        |
| 7.8  | 🟡 Niedrig  | `tests/test_unit.py`         | Fehlende Tests für `_validate_zone_syntax` / `dry_run` / `_check_path` |
| 7.9  | 🟡 Niedrig  | `pyproject.toml:29`          | `pytest-cov` nicht in Abhängigkeiten                 |
| 7.10 | 🟡 Niedrig  | `dnsjinja.py:271`            | `sys.tracebacklimit=0` nur im `__main__`-Block       |
| 7.11 | 🟡 Niedrig  | `__init__.py:5`              | Statische `__version__` statt `importlib.metadata`   |
| 8.1  | 🔵 Idee     | `pyproject.toml`             | `ruff` für Linting konfigurieren                     |
| 8.2  | 🔵 Idee     | `pyproject.toml`             | `mypy` für Typ-Prüfung konfigurieren                 |
| 8.3  | 🔵 Idee     | `dnsjinja.py:5`              | `typing.Required` benötigt Python ≥ 3.11             |
| 8.4  | 🔵 Idee     | `dnsjinja.py:61–65`          | `--create-missing` mit Bestätigung absichern         |
