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

## 1  Verbesserungsideen

### 1.1  Validierung der Zone-File-Syntax vor dem Upload 🔵
Gerenderte Zone-Files werden nicht syntaktisch geprüft. Ein ungültiges
Zone-File wird hochgeladen und Hetzner liefert dann einen Fehler zurück.
`dnspython` hat einen Zone-Parser (`dns.zone.from_text()`), der vor dem
Upload aufgerufen werden könnte.

---

### 1.2  SOA-Serial im `_create_zone_data()`-Rückgabewert mitführen 🔵
Zur Behebung von Bug 2.3 bietet sich an, `_create_zone_data()` ein
`dict[str, tuple[str, str]]` (domain → (zonefile_content, serial)) zurückgeben
zu lassen. So ist die Serial für `write_zone_files()` und zukünftige
Verwendungen direkt verfügbar.

---

### 1.3  `--dry-run`-Flag 🔵
Vor einem Upload wäre eine Vorschau-Option nützlich: Zone-File rendern und
ausgeben, aber weder schreiben noch hochladen. Besonders hilfreich für CI-Pipelines,
die Pull-Requests validieren.

---

### 1.4  Template-Namen gegen Traversal absichern 🔵
`env.get_template(d["template"])` akzeptiert den Template-Namen direkt aus der
Config. Jinja2's `FileSystemLoader` verhindert Pfad-Traversal durch seine
Sandbox, aber ein explizites Whitelist-Pattern
(`^[a-zA-Z0-9._-]+\.tpl$` o. ä.) würde die Intention klarer ausdrücken.

---

## 2  Bugs

### 2.1  `__main__.py` – fehlender `import sys` 🔴
**Datei:** `src/dnsjinja/__main__.py:5`

```python
from .dnsjinja import main

if __name__ == '__main__':
    sys.tracebacklimit = 0   # ← sys ist nicht importiert!
    main()
```

`sys` wird in Zeile 5 verwendet, aber nicht importiert. Jeder Aufruf via
`python -m dnsjinja` endet mit einem `NameError: name 'sys' is not defined`,
bevor `main()` überhaupt erreicht wird.

**Empfehlung:** `import sys` am Anfang der Datei hinzufügen.

---

### 2.2  `explore_hetzner.py` – Token im Klartext sichtbar 🟠
**Datei:** `src/dnsjinja/explore_hetzner.py:13`

```python
auth_api_token = auth_api_token or input('Hetzner API-Token (Bearer): ')
```

Das Security-Finding 1.1 (`input()` statt `getpass.getpass()`) wurde in
`dnsjinja.py` behoben, aber `explore_hetzner.py` enthält dasselbe Muster
noch unverändert. Das Token wird beim Tippen am Bildschirm angezeigt.

**Empfehlung:** `getpass.getpass('Hetzner API-Token (Bearer): ')` verwenden.

---

### 2.3  `explore_hetzner.py` – Breites `except Exception` 🟡
**Datei:** `src/dnsjinja/explore_hetzner.py:25,30`

```python
except Exception as e:
    print(f'Fehler beim Abfragen der Zonen: {e}')
...
except Exception as e:
    print(f'Fehler beim Schreiben von {self.output}: {str(e)}')
```

Beide Blöcke fangen `Exception` zu weit gefasst ab – dasselbe Problem wie
Finding 3.2 in `dnsjinja.py`, dort bereits behoben.

**Empfehlung:** Spezifische Typen: `hcloud.APIException` bzw. `OSError`.

---

## 3  Code-Vereinfachung

### 3.1  `_check_dir` / `_check_file` zusammenführen 🟡
**Datei:** `src/dnsjinja/dnsjinja.py:29–47`

```python
@staticmethod
def _check_dir(path_to_check: str, basedir: str, typ: str) -> Path:
    ...
    if not path_to_check.is_dir():
        print(f'{typ} {path_to_check} existiert nicht oder ist kein Verzeichnis.')

@staticmethod
def _check_file(path_to_check: str, basedir: str, typ: str) -> Path:
    ...
    if not path_to_check.is_file():
        print(f'{typ} {path_to_check} existiert nicht oder ist keine Datei.')
```

Die beiden Methoden sind zu 95% identisch – nur die Prüfmethode und das
Fehlerwort unterscheiden sich. Code-Duplikation, die bei Änderungen
(z. B. Fehlerformat) doppelt gepflegt werden muss.

**Empfehlung:** Eine gemeinsame `_check_path()`-Methode:
```python
@staticmethod
def _check_path(path: str, basedir: str, typ: str, expect: str = 'dir') -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = Path(basedir) / p
    valid = p.is_dir() if expect == 'dir' else p.is_file()
    if not valid:
        kind = 'Verzeichnis' if expect == 'dir' else 'Datei'
        print(f'{typ} {p} existiert nicht oder ist kein(e) {kind}.')
        sys.exit(1)
    return p
```

---

### 3.2  Redundantes `hetzner_domains`-Set in `_prepare_zones()` 🟡
**Datei:** `src/dnsjinja/dnsjinja.py:53–55`

```python
hetzner_domains = set(z.name for z in all_zones)    # Set aus Zone-Namen
hetzner_zones = {z.name: z for z in all_zones}       # Dict Name → Zone
```

Beide werden aus derselben Liste aufgebaut. `hetzner_zones.keys()` ist ein
`KeysView` der sich exakt wie ein Set verhält; `hetzner_domains` ist
überflüssig.

**Empfehlung:** `hetzner_domains` entfernen, stattdessen direkt
`hetzner_zones.keys()` für die Set-Operationen verwenden:
```python
hetzner_zones = {z.name: z for z in all_zones}
config_domains = set(self.config['domains'].keys())
for d in sorted(config_domains - hetzner_zones.keys()):
    ...
for d in (hetzner_zones.keys() - config_domains):
    ...
```

---

### 3.3  `UploadError.msgfmt` – toter Code 🟡
**Datei:** `src/dnsjinja/dnsjinja.py:19–22`

```python
class UploadError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.msgfmt = message    # ← wird nirgends gelesen
```

`self.msgfmt` wird in der gesamten Codebasis nie ausgelesen.
`Exception.__init__(message)` speichert die Message bereits unter `args[0]`
und ist über `str(e)` erreichbar.

**Empfehlung:**
```python
class UploadError(Exception):
    pass
```

---

### 3.4  Unbenutzte Loop-Variable `d` 🟡
**Datei:** `src/dnsjinja/dnsjinja.py:218,239`

```python
for domain, d in self.config["domains"].items():   # d nie genutzt
    self.upload_zone(domain)
...
for domain, d in self.config["domains"].items():   # d nie genutzt
    self.backup_zone(domain)
```

`d` (der Domain-Config-Dict) wird in `upload_zones()` und `backup_zones()`
nie gelesen. Linter wie `ruff` oder `pylint` warnen darüber.

**Empfehlung:**
```python
for domain in self.config["domains"]:
    self.upload_zone(domain)
```

---

### 3.5  Properties ohne Validierungslogik 🟡
**Datei:** `src/dnsjinja/dnsjinja.py:134–160`

```python
@property
def upload(self) -> bool:
    return self._upload

@upload.setter
def upload(self, new_status: bool) -> None:
    self._upload = new_status
```

Die drei Properties für `upload`, `backup` und `write_zone` sind reine
Getter/Setter ohne jede Validierungs- oder Konvertierungslogik. Sie führen
`_upload`/`_backup`/`_write_zone` als private Attribute ein, die nur einen
zusätzlichen Indirektion-Layer erzeugen.

**Empfehlung:** Direkte öffentliche Attribute in `__init__`:
```python
self.upload = upload
self.backup = backup
self.write_zone = write_zone
```
Sollte später Validierung nötig werden, können die Properties dann eingeführt
werden (kein Breaking Change).

---

## 4  Robustheit

### 4.1  `exit_on_error.py` – `int(ec)` ohne Fehlerbehandlung 🟠
**Datei:** `src/dnsjinja/exit_on_error.py:26`

```python
sys.exit(int(ec))
```

Wenn die Exit-Code-Datei korrupten Inhalt enthält (z. B. leer, abgebrochener
Schreibvorgang, Encoding-Problem), wirft `int(ec)` einen `ValueError` und
`exit_on_error` stürzt mit Traceback ab, anstatt sauber zu scheitern.

**Empfehlung:**
```python
try:
    sys.exit(int(ec.strip()))
except ValueError:
    print(f'Ungültiger Exit-Code in Datei: {ec!r}', file=sys.stderr)
    sys.exit(1)
```

---

### 4.2  `myloadenv.py` – lädt *alle* .env-Dateien statt nur die erste 🟡
**Datei:** `src/dnsjinja/myloadenv.py:33–37`

```python
for p in env_paths:
    for n in env_names:
        file = Path(p) / Path(n)
        if file.exists():
            dotenv.load_dotenv(file)   # ← kein break, kein return
```

Die verschachtelte Schleife bricht nie ab. Werden z. B. sowohl
`~/.config/dnsjinja.env` als auch `./dnsjinja.env` gefunden, werden beide
geladen – spätere Werte überschreiben frühere. In `tests/conftest.py` wird
dagegen bewusst beim ersten Treffer abgebrochen (`break`). Das Verhalten
sollte einheitlich und dokumentiert sein.

**Empfehlung:** Entweder nach der ersten gefundenen Datei abbrechen
(`return` nach `load_dotenv()`), oder das bewusste Merge-Verhalten im
Docstring dokumentieren und die Reihenfolge nach Priorität ordnen (höchste
Priorität zuletzt laden, damit sie nicht überschrieben wird).

---

### 4.3  JSON-Schema: `additionalItems: True` wirkungslos 🟡
**Datei:** `src/dnsjinja/dnsjinja_config_schema.py:82`

```json
"additionalItems": True,
"items": { ... }
```

In JSON Schema Draft 7 gilt `additionalItems` nur, wenn `items` ein
**Array** (Tuple-Validierung) ist. Ist `items` ein Schema-Objekt (wie hier),
hat `additionalItems` keine Wirkung. Das Keyword wird in Draft 2019-09 und
später umbenannt (`unevaluatedItems`).

**Empfehlung:** Zeile `"additionalItems": True` entfernen.

---

### 4.4  JSON-Schema: `anyOf` mit nur einem Element 🟡
**Datei:** `src/dnsjinja/dnsjinja_config_schema.py:85–94`

```json
"items": {
    "anyOf": [
        {
            "type": "string",
            "format": "ipv4"
        }
    ]
}
```

`anyOf` mit exakt einem Element ist semantisch äquivalent zu dem Element
selbst. Es erzeugt unnötige Verschachtelung und war vermutlich ein Artefakt
aus einem Schema-Generator.

**Empfehlung:** Das `anyOf`-Wrapper-Objekt entfernen:
```json
"items": {
    "type": "string",
    "format": "ipv4",
    "title": "name-servers",
    "description": "Name server IP address",
    "default": ""
}
```

---

## 5  Wartbarkeit

### 5.1  `__init__` ohne Type Hints 🟡
**Datei:** `src/dnsjinja/dnsjinja.py:78`

```python
def __init__(self, upload=False, backup=False, write_zone=False,
             datadir="", config_file="config/config.json",
             auth_api_token="", create_missing=False):
```

Alle anderen Methoden der Klasse haben Type Hints. `__init__` ist die
primäre öffentliche Schnittstelle der Klasse und sollte ebenfalls annotiert
sein – insbesondere für IDE-Support und `mypy`.

**Empfehlung:**
```python
def __init__(self, upload: bool = False, backup: bool = False,
             write_zone: bool = False, datadir: str = "",
             config_file: str = "config/config.json",
             auth_api_token: str = "", create_missing: bool = False) -> None:
```

---

### 5.2  `__init__.py` ohne `__version__` und `__all__` 🟡
**Datei:** `src/dnsjinja/__init__.py`

```python
from .dnsjinja import DNSJinja, main
from .explore_hetzner import main as explore_main
from .exit_on_error import run as exit_on_error
```

Die Versionsnummer ist nur in `setup.cfg` hinterlegt, nicht programmatisch
erreichbar (`import dnsjinja; dnsjinja.__version__` schlägt fehl).
`__all__` fehlt – ohne es exportiert `from dnsjinja import *` unbeabsichtigt
alle importierten Namen.

**Empfehlung:**
```python
__version__ = '0.3.0'
__all__ = ['DNSJinja', 'main', 'explore_main', 'exit_on_error']
```

---

### 5.3  Testlücke: Schema-Validierung 🟡
**Datei:** `tests/test_unit.py`

Es gibt keinen Test, der prüft, ob eine Config **ohne** das Pflichtfeld
`template` vom Schema abgewiesen wird. Das `patternProperties`-Bug (Finding
2.5) hatte dafür gesorgt, dass diese Validierung nie griff – nach dem Fix
sollte ein Regressionstest den korrekten Ablauf absichern.

**Empfehlung:** Neuer Test in `TestTokenUndPfad` oder eigener
`TestConfigValidierung`-Klasse:
```python
def test_config_ohne_template_schlaegt_fehl(self, data_dir, mock_client,
                                             mock_dns_resolver):
    config_path = data_dir / 'config' / 'config.json'
    config_path.write_text(json.dumps({
        "global": { ... },
        "domains": { "test.com": {} }   # kein 'template'-Feld
    }), encoding='utf-8')
    with pytest.raises(SystemExit) as exc_info:
        DNSJinja(datadir=str(data_dir), config_file=str(config_path),
                 auth_api_token='test-token')
    assert exc_info.value.code == 1
```

---

### 5.4  Testlücke: Template-Rendering 🟡
**Datei:** `tests/test_unit.py`

Kein Test prüft, ob `domain` und `soa_serial` korrekt in das Zone-File
gerendert werden. `_create_zone_data()` ist die zentrale Funktion des Tools –
ein Jinja2-Syntaxfehler im Template oder eine falsche Variable würde im
Zone-Inhalt unbemerkt bleiben.

**Empfehlung:**
```python
def test_template_variablen_werden_substituiert(self, data_dir, config_file,
                                                 mock_client, mock_dns_resolver):
    dj = make_dnsjinja(data_dir, config_file, mock_client, mock_dns_resolver)
    zone = dj.zones['example.com']
    assert '$ORIGIN example.com.' in zone
    assert dj._serials['example.com'] in zone
```

---

## 6  Modernisierungspotenzial

Stand: 2026-02-15 – Empfehlungen für "more Pythonic" Code und zeitgemäßere Bibliotheken

---

### M.1  `appdirs` → `platformdirs` 🟠
**Datei:** `src/dnsjinja/myloadenv.py:1,14` · `setup.cfg:install_requires`

```python
# aktuell
import appdirs
userconfig = Path(appdirs.user_config_dir(module, ''))
```

`appdirs` v1.4.4 (letztes Release: 2020) wird nicht mehr gepflegt.
Der offizielle Nachfolger ist **`platformdirs`** – entwickelt von denselben
Maintainern, aktiv gepflegt, API-kompatibel. `hcloud` selbst listet
`platformdirs` als Abhängigkeit, `appdirs` hingegen nicht.

**Empfehlung:** Drop-in-Ersatz:
```python
# nachher
import platformdirs
userconfig = Path(platformdirs.user_config_dir(module, ''))
```
Zusätzlich in `setup.cfg`: `appdirs>=1.4` → `platformdirs>=4.0`.

---

### M.2  `Path().absolute()` → `Path.cwd()` 🟡
**Datei:** `src/dnsjinja/myloadenv.py:16`

```python
dot = Path().absolute()   # aktuell
dot = Path.cwd()          # idiomatisch
```

`Path()` ohne Argumente erzeugt `.` (relativer Pfad zum CWD). `.absolute()`
wandelt ihn in einen absoluten Pfad um. Der klare, intendierte Ausdruck für
„aktuelles Arbeitsverzeichnis" ist `Path.cwd()`.

---

### M.3  `setup.cfg` → `pyproject.toml` (PEP 621) 🟡
**Datei:** `setup.cfg`, `pyproject.toml`

Seit PEP 621 (Python 3.11) ist `[project]` in `pyproject.toml` der
Standard für Paket-Metadaten. `setup.cfg` ist ein Legacy-Format von
`setuptools`. Alle Metadaten (Name, Version, Dependencies, Entry-Points,
Classifiers) können in `pyproject.toml` migriert werden – `setup.cfg`
fällt danach vollständig weg.

**Empfehlung:** `setup.cfg` in `pyproject.toml` überführen:
```toml
[project]
name = "dnsjinja-kaijen"
version = "0.3.0"
requires-python = ">=3.10"
dependencies = [
    "Jinja2>=3.0",
    "hcloud>=2.0",
    ...
]

[project.scripts]
dnsjinja = "dnsjinja:main"
explore_hetzner = "dnsjinja:explore_main"
exit_on_error = "dnsjinja:exit_on_error"
```

---

### M.4  `pathlib`-Methoden statt `open()` 🟡
**Datei:** `src/dnsjinja/exit_on_error.py:21–22`

```python
# aktuell
with open(exit_code_file, "r", encoding="utf8") as ecf:
    ec = ecf.read()

# idiomatisch
ec = exit_code_file.read_text(encoding='utf-8')
```

`Path.read_text()` und `Path.write_text()` sind seit Python 3.5 verfügbar
und kürzer als das `with open()`-Muster. Sie sind idiomatisch für einfache
Datei-Lese/-Schreib-Operationen ohne sequenzielle Verarbeitung.

Weitere Kandidaten: `exit_on_error.py:17` (`Path.exists()`-Check vor
`read_text()`).

---

### M.5  `print()` → `click.echo()` 🟡
**Datei:** `src/dnsjinja/dnsjinja.py` (alle `print()`-Aufrufe)

Click empfiehlt `click.echo()` statt `print()` für CLI-Ausgaben, da es:
- Encoding-Fehler auf Windows abfängt (`errors='replace'`)
- `stderr`-Ausgabe einfach macht: `click.echo(msg, err=True)`
- Mock-freundlicher in Click-Tests ist

Auf Linux ist der Unterschied funktional transparent, aber die konsequente
Nutzung bereitet ein `--quiet`-Flag vor und folgt den Click-Konventionen.

---

### M.6  `print()` → `logging`-Modul 🟡
**Datei:** gesamte Codebasis

Alle Statusmeldungen und Fehler werden über `print()` ausgegeben. Das
`logging`-Modul wäre angemessener:

| Aktuell | Mit logging |
|---------|-------------|
| `print(f'{d} neu angelegt')` | `logging.info('%s wurde angelegt', d)` |
| `print(f'Fehler: {e}')` | `logging.error('Fehler: %s', e)` |
| (kein Debug) | `logging.debug('Resolver: %s', serial)` |

Vorteile: Verbosity-Kontrolle via `-v`/`-q`, File-Handler für Logs,
strukturierte CI-Ausgabe.

**Hinweis:** Kombination mit `click` üblich via
`logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)`.

---

### M.7  `jsonschema` → `pydantic` v2 (Designentscheidung) 🔵
**Datei:** `src/dnsjinja/dnsjinja_config_schema.py`, `dnsjinja.py`

Die aktuelle JSON-Schema-Validierung nutzt ein 145-Zeilen-Dict. Mit
**Pydantic v2** (dem De-facto-Standard für Python-Config-Validierung) würde
die Config zur typisierten Klasse:

```python
from pydantic import BaseModel, Field, field_validator

class GlobalConfig(BaseModel):
    zone_files: str = Field(alias='zone-files')
    zone_backups: str = Field(alias='zone-backups')
    templates: str
    name_servers: list[str] = Field(alias='name-servers', min_length=1)
    dns_api_base: str = Field(
        alias='dns-api-base',
        default='https://api.hetzner.cloud/v1',
        pattern='^https://'
    )

class DnsJinjaConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    globals: GlobalConfig = Field(alias='global')
    domains: dict[str, DomainConfig]
```

Vorteile: IDE-Autovervollständigung, automatische Typkonvertierung,
klare Fehlermeldungen, `extra='forbid'` für strikte Validierung.
Nachteil: Neue Abhängigkeit, größere Migration.

---

### M.8  Moderne Type-Annotation-Syntax (Python 3.10+) 🟡
**Datei:** `src/dnsjinja/dnsjinja.py`

Da `setup.cfg` `python_requires = >=3.10` vorschreibt, können die modernen
Union- und Collection-Syntax-Formen genutzt werden:

```python
# alt (Python 3.9 kompatibel)
from typing import Optional, Dict, List
def foo(x: Optional[str] = None) -> Dict[str, List[str]]: ...

# neu (Python 3.10+)
def foo(x: str | None = None) -> dict[str, list[str]]: ...
```

Betrifft: `self._serials: dict = {}` in `dnsjinja.py:131` sollte
`self._serials: dict[str, str] = {}` werden.

---

### M.9  `TypedDict` für Domain-Konfiguration 🟡
**Datei:** `src/dnsjinja/dnsjinja.py`

Die `config['domains'][domain]`-Dicts werden zur Laufzeit durch
`_prepare_zones()` um `zone-id` und `zone-file` erweitert. Aktuell sind
diese Dicts untypisiert – IDE und `mypy` haben keine Information über die
verfügbaren Schlüssel.

**Empfehlung:** `TypedDict` für IDE-Support:
```python
from typing import TypedDict, Required

class DomainConfig(TypedDict, total=False):
    template: Required[str]   # Pflichtfeld
    zone_id: str              # gesetzt von _prepare_zones()
    zone_file: str            # gesetzt von _prepare_zones()
```

Dies wäre ein vorbereitender Schritt für eine eventuelle Pydantic-Migration
(Finding M.7).

---

## Zusammenfassung

| # | Schweregrad | Datei / Zeile | Kurzbeschreibung |
|---|-------------|---------------|-----------------|
| 1.1 | 🔵 | – | Validierung Zone-File-Syntax vor Upload |
| 1.2 | 🔵 | – | SOA-Serial im Rückgabewert mitführen |
| 1.3 | 🔵 | – | `--dry-run`-Flag |
| 1.4 | 🔵 | – | Template-Namen gegen Traversal absichern |
| 2.1 | 🔴 | `__main__.py:5` | `import sys` fehlt → `NameError` |
| 2.2 | 🟠 | `explore_hetzner.py:13` | Token über `input()` sichtbar |
| 2.3 | 🟡 | `explore_hetzner.py:25,30` | Breites `except Exception` |
| 3.1 | 🟡 | `dnsjinja.py:29–47` | `_check_dir`/`_check_file` zusammenführen |
| 3.2 | 🟡 | `dnsjinja.py:53–55` | Redundantes `hetzner_domains`-Set |
| 3.3 | 🟡 | `dnsjinja.py:19–22` | `UploadError.msgfmt` toter Code |
| 3.4 | 🟡 | `dnsjinja.py:218,239` | Unbenutzte Loop-Variable `d` |
| 3.5 | 🟡 | `dnsjinja.py:134–160` | Properties ohne Logik |
| 4.1 | 🟠 | `exit_on_error.py:26` | `int(ec)` ohne Fehlerbehandlung |
| 4.2 | 🟡 | `myloadenv.py:33–37` | Alle .env-Dateien statt nur erste laden |
| 4.3 | 🟡 | `dnsjinja_config_schema.py:82` | `additionalItems` wirkungslos |
| 4.4 | 🟡 | `dnsjinja_config_schema.py:85–94` | `anyOf` mit einem Element |
| 5.1 | 🟡 | `dnsjinja.py:78` | Type Hints für `__init__` |
| 5.2 | 🟡 | `__init__.py` | `__version__` und `__all__` fehlen |
| 5.3 | 🟡 | `test_unit.py` | Testlücke: Schema-Validierung |
| 5.4 | 🟡 | `test_unit.py` | Testlücke: Template-Rendering |
| M.1 | 🟠 | `myloadenv.py:1,14` | `appdirs` (abandoned) → `platformdirs` |
| M.2 | 🟡 | `myloadenv.py:16` | `Path().absolute()` → `Path.cwd()` |
| M.3 | 🟡 | `setup.cfg` | `setup.cfg` → `pyproject.toml` (PEP 621) |
| M.4 | 🟡 | `exit_on_error.py:21–22` | `open()` → `Path.read_text()` |
| M.5 | 🟡 | `dnsjinja.py` (alle) | `print()` → `click.echo()` |
| M.6 | 🟡 | gesamte Codebasis | `print()` → `logging`-Modul |
| M.7 | 🔵 | `dnsjinja_config_schema.py` | `jsonschema` → `pydantic` v2 |
| M.8 | 🟡 | `dnsjinja.py` | Moderne Type-Syntax (`str \| None`, `dict[str, str]`) |
| M.9 | 🟡 | `dnsjinja.py` | `TypedDict` für Domain-Konfiguration |
