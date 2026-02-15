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

## 2  Robustheit

### 2.1  `exit_on_error.py` – `int(ec)` ohne Fehlerbehandlung 🟠
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

### 2.3  JSON-Schema: `additionalItems: True` wirkungslos 🟡
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

### 2.4  JSON-Schema: `anyOf` mit nur einem Element 🟡
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

## 3  Wartbarkeit

### 3.1  `__init__` ohne Type Hints 🟡
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

### 3.2  `__init__.py` ohne `__version__` und `__all__` 🟡
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

### 3.3  Testlücke: Schema-Validierung 🟡
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

### 3.4  Testlücke: Template-Rendering 🟡
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

## 4  Modernisierungspotenzial

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
| 2.1 | 🟠 | `exit_on_error.py:26` | `int(ec)` ohne Fehlerbehandlung |
| 2.3 | 🟡 | `dnsjinja_config_schema.py:82` | `additionalItems` wirkungslos |
| 2.4 | 🟡 | `dnsjinja_config_schema.py:85–94` | `anyOf` mit einem Element |
| 3.1 | 🟡 | `dnsjinja.py:78` | Type Hints für `__init__` |
| 3.2 | 🟡 | `__init__.py` | `__version__` und `__all__` fehlen |
| 3.3 | 🟡 | `test_unit.py` | Testlücke: Schema-Validierung |
| 3.4 | 🟡 | `test_unit.py` | Testlücke: Template-Rendering |
| M.3 | 🟡 | `setup.cfg` | `setup.cfg` → `pyproject.toml` (PEP 621) |
| M.4 | 🟡 | `exit_on_error.py:21–22` | `open()` → `Path.read_text()` |
| M.5 | 🟡 | `dnsjinja.py` (alle) | `print()` → `click.echo()` |
| M.6 | 🟡 | gesamte Codebasis | `print()` → `logging`-Modul |
| M.7 | 🔵 | `dnsjinja_config_schema.py` | `jsonschema` → `pydantic` v2 |
| M.8 | 🟡 | `dnsjinja.py` | Moderne Type-Syntax (`str \| None`, `dict[str, str]`) |
| M.9 | 🟡 | `dnsjinja.py` | `TypedDict` für Domain-Konfiguration |
