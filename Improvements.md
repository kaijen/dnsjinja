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
| M.3 | 🟡 | `setup.cfg` | `setup.cfg` → `pyproject.toml` (PEP 621) |
| M.4 | 🟡 | `exit_on_error.py:21–22` | `open()` → `Path.read_text()` |
| M.5 | 🟡 | `dnsjinja.py` (alle) | `print()` → `click.echo()` |
| M.6 | 🟡 | gesamte Codebasis | `print()` → `logging`-Modul |
| M.7 | 🔵 | `dnsjinja_config_schema.py` | `jsonschema` → `pydantic` v2 |
| M.8 | 🟡 | `dnsjinja.py` | Moderne Type-Syntax (`str \| None`, `dict[str, str]`) |
| M.9 | 🟡 | `dnsjinja.py` | `TypedDict` für Domain-Konfiguration |
