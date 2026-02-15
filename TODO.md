## TODOs

- [x] Umstellung der API auf die neue Cloud-API von Hetzner
- [x] Erstellung einer Dokumentation für dnsjinja
  - [x] Run in virtual Environment
  - [x] Run in Docker
  - [x] Run in Github Workflow
  - [x] Erläuterung der Struktur der Konfiguration (Input JSON und jinja2 Dateien)
- [x] Docker Container zum Ausrollen
- [x] Docker Container zum Entwickeln bei dem das Modul mit `pip install -e .` installiert uird
- [x] Umschreiben auf [Hetzner Cloud API Python Bibliothek](https://github.com/hetznercloud/hcloud-python)

---

## Offene Verbesserungen (aus Code Review)

### Security

- [x] **1.1 – Token-Eingabe maskieren** (`dnsjinja.py:190,214`)

  `input()` durch `getpass.getpass()` ersetzen, damit der Token nicht im
  Terminal erscheint und nicht in der Shell-History landet:

  ```python
  import getpass
  # vorher:
  self.auth_api_token = input("Auth-API-Token: ")
  # nachher:
  self.auth_api_token = getpass.getpass("Auth-API-Token: ")
  ```

  Beide Stellen betroffen: `upload_zones()` und `backup_zones()`.

---

- [x] **1.2 – Exit-Code-Datei mit PID eindeutig machen** (`dnsjinja.py:69`, `exit_on_error.py:8`)

  Der feste Dateiname `/tmp/dnsjinja.exit.txt` ermöglicht Konflikte zwischen
  mehreren gleichzeitig laufenden Prozessen. Den Dateinamen mit der PID
  parametrisieren und `exit_on_error` den Pfad als Argument übergeben:

  ```python
  # dnsjinja.py – __init__:
  import os
  self.exit_status_file = Path(tempfile.gettempdir()) / f"dnsjinja.{os.getpid()}.exit.txt"
  ```

  ```python
  # exit_on_error.py – run() erhält den Pfad als Option:
  @click.command()
  @click.option('--exit-file', envvar='DNSJINJA_EXIT_FILE', default='', help="Pfad zur Exit-Code-Datei")
  def run(exit_file):
      if exit_file:
          exit_code_file = Path(exit_file)
      else:
          exit_code_file = Path(tempfile.gettempdir()) / "dnsjinja.exit.txt"
      ...
  ```

  In `run()` (`dnsjinja.py`) den Pfad via Umgebungsvariable übergeben:

  ```python
  os.environ['DNSJINJA_EXIT_FILE'] = str(dnsjinja.exit_status_file)
  ```

---

- [x] **1.3 – Nur HTTPS als API-Endpunkt erlauben** (`dnsjinja_config_schema.py:71`)

  ```python
  # vorher:
  "pattern": "^https?://"
  # nachher:
  "pattern": "^https://"
  ```

---

### Bugs

- [x] **2.1 – Variable-Shadowing in Config-Lesefehler-Meldung** (`dnsjinja.py:75,79`)

  Die `with`-Variable umbenennen, damit `self.config_file` im `except`-Block
  den lesbaren Pfad liefert:

  ```python
  # vorher:
  with open(self.config_file, encoding='utf-8') as config_file:
      self.config = json.load(config_file)
  ...
  except Exception as e:
      print(f'Konfigurationsdatei {config_file} konnte nicht ...')
  #                                 ^^^ zeigt File-Handle-Objekt

  # nachher:
  with open(self.config_file, encoding='utf-8') as cfg_fh:
      self.config = json.load(cfg_fh)
  ...
  except Exception as e:
      print(f'Konfigurationsdatei {self.config_file} konnte nicht ...')
  ```

---

- [x] **2.2 – SOA-Serial-Überlauf bei Suffix 99** (`dnsjinja.py:152`)

  In der Praxis selten (99 Uploads pro Tag), aber korrekt abfangen.
  Empfehlung: Warnung und Abbruch statt stiller Erzeugung einer
  ungültigen 11-stelligen Seriennummer:

  ```python
  suffix_int = int(soa_serial[-2:]) + 1
  if suffix_int > 99:
      print(f'SOA-Zähler für {domain} hat 99 erreicht – kein weiterer Upload heute möglich.')
      sys.exit(1)
  serial_suffix = f'{suffix_int:02d}'
  ```

---

- [x] **2.3 – Serial aus `_create_zone_data()` cachen, nicht erneut abfragen** (`dnsjinja.py:161,168`)

  **Hintergrund:** Die alte Hetzner DNS-API (`dns.hetzner.com`) hat den
  SOA-Serial beim Import automatisch hochgezählt. Die neue Cloud-API
  (`api.hetzner.cloud/v1`) übernimmt den Serial **exakt so, wie er im
  hochgeladenen Zone-File steht** – es findet kein Auto-Increment statt.

  Der in `_create_zone_data()` berechnete Serial `S` ist also genau der
  Serial, der nach dem Upload bei Hetzner steht. `write_zone_files()` fragt
  den Serial aber via `_new_zone_serial()` erneut aus dem DNS ab (eine zweite
  Netzwerkabfrage). Da der Upload zu diesem Zeitpunkt noch nicht stattgefunden
  hat, liefert die zweite Abfrage denselben *alten* Serial wie die erste und
  berechnet daraus erneut `S` – was in der Regel übereinstimmt. Bei
  Mitternacht oder einem parallelen Prozess kann es jedoch zu einer
  Abweichung kommen.

  Lösung: Den berechneten Serial in `_create_zone_data()` je Domain
  speichern und in `write_zone_files()` wiederverwenden:

  ```python
  # __init__ – Instanzvariable anlegen:
  self._serials: dict = {}

  # _create_zone_data() – Serial speichern:
  def _create_zone_data(self) -> dict:
      zones = {}
      for domain, d in self.config["domains"].items():
          template = self.env.get_template(d["template"])
          soa_serial = self._new_zone_serial(domain)
          self._serials[domain] = soa_serial          # ← neu
          zones[domain] = template.render(domain=domain, soa_serial=soa_serial, **d)
      return zones

  # write_zone_files() – gespeicherten Serial nutzen statt _new_zone_serial():
  def write_zone_files(self) -> None:
      if not self.write_zone:
          return
      for domain, d in self.config["domains"].items():
          zonefile = self.zone_files_dir / Path(
              d['zone-file'] + f'.{self._serials[domain]}'   # ← statt _new_zone_serial()
          )
          ...
  ```

  Damit sind Dateiinhalt und Dateiname garantiert konsistent und die Anzahl
  der DNS-Abfragen halbiert sich.

---

- [x] **2.4 – `_check_dir`: `is_dir()` statt `exists()`** (`dnsjinja.py:27–33`)

  ```python
  # vorher:
  if not path_to_check.exists():
      print(f'{typ} {path_to_check} existiert nicht.')
      sys.exit(1)

  # nachher – Verzeichnis und Konfigurationsdatei getrennt prüfen:
  @staticmethod
  def _check_dir(path_to_check: str, basedir: str, typ: str) -> Path:
      path_to_check = Path(path_to_check)
      if not path_to_check.is_absolute():
          path_to_check = Path(basedir) / path_to_check
      if not path_to_check.is_dir():
          print(f'{typ} {path_to_check} existiert nicht oder ist kein Verzeichnis.')
          sys.exit(1)
      return path_to_check

  @staticmethod
  def _check_file(path_to_check: str, basedir: str, typ: str) -> Path:
      path_to_check = Path(path_to_check)
      if not path_to_check.is_absolute():
          path_to_check = Path(basedir) / path_to_check
      if not path_to_check.is_file():
          print(f'{typ} {path_to_check} existiert nicht oder ist keine Datei.')
          sys.exit(1)
      return path_to_check
  ```

  In `__init__` für `config_file` dann `_check_file` statt `_check_dir`
  aufrufen.

---

- [x] **2.5 – `patternProperties` (camelCase) im JSON-Schema** (`dnsjinja_config_schema.py:106`)

  Der Schlüssel `pattern_properties` (Unterstrich) ist kein gültiges
  JSON-Schema-Keyword und wird von `jsonschema` ignoriert. Dadurch wird
  `"required": ["template"]` für Domain-Einträge nie geprüft.

  ```python
  # vorher:
  "pattern_properties": {
      "\"^.*$\"": { ... }
  }

  # nachher:
  "patternProperties": {
      "^.*$": { ... }
  }
  ```

  Außerdem war das Pattern `"\"^.*$\""` (mit Escape-Anführungszeichen)
  falsch – korrekt ist `"^.*$"` ohne die zusätzlichen Anführungszeichen.

---

- [x] **2.6 – Interaktiver Client ohne `api_endpoint`** (`dnsjinja.py:89,191,215`)

  `api_base` als Instanzvariable speichern und beim interaktiven
  Client-Neuaufbau verwenden:

  ```python
  # __init__ – api_base als self speichern:
  self._api_base = self.config['global'].get('dns-api-base', self.DEFAULT_API_BASE).rstrip('/')
  self.client = Client(token=self.auth_api_token, api_endpoint=self._api_base)

  # upload_zones() und backup_zones() – api_base einbeziehen:
  self.client = Client(token=self.auth_api_token, api_endpoint=self._api_base)
  ```

---

- [x] **2.7 – Toter Code `global exit_status` entfernen** (`dnsjinja.py:237`)

  ```python
  # vorher:
  def main():
      global exit_status
      load_env()
      run()

  # nachher:
  def main():
      load_env()
      run()
  ```

---

- [x] **2.8 – Duplikat `python-dotenv` in `setup.cfg` entfernen** (`setup.cfg:30`)

  ```ini
  install_requires =
      Jinja2
      hcloud
      dnspython
      Click
      python-dotenv   # ← erste Zeile behalten
      jsonschema
      appdirs
                      # ← zweite Zeile (python-dotenv) löschen
  ```

---

### Code-Qualität

- [x] **3.1 – Frühzeitig prüfen ob Token vorhanden** (`dnsjinja.py:89`)

  Der `hcloud.Client` wird immer initialisiert, auch ohne Token.
  `_prepare_zones()` schlägt dann mit einem kryptischen API-Fehler fehl
  statt mit einer klaren Meldung. Prüfung vor den API-Aufrufen:

  ```python
  # Nach den _check_dir-Aufrufen, vor Client-Initialisierung:
  if not auth_api_token:
      print('Kein API-Token angegeben. Bitte --auth-api-token oder DNSJINJA_AUTH_API_TOKEN setzen.')
      sys.exit(1)
  ```

  Die interaktive Abfrage in `upload_zones()` und `backup_zones()` kann
  damit entfallen.

---

- [x] **3.2 – Spezifische Exception-Typen statt `except Exception`** (`dnsjinja.py:49,61,78,144,173,207`)

  Konkrete Typen fangen erwartete Fehler ab; `Exception` als Fallback
  bleibt möglich, sollte aber explizit kommentiert sein:

  ```python
  # Config-Lesen (Zeile 78):
  except (json.JSONDecodeError, jsonschema.ValidationError, OSError) as e:

  # _prepare_zones – create (Zeile 49):
  except hcloud.APIException as e:

  # _prepare_zones – outer (Zeile 61):
  except (hcloud.HCloudException, OSError) as e:

  # _get_zone_serial (Zeile 144):
  except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
          dns.resolver.NoNameservers, dns.exception.DNSException) as e:

  # write_zone_files (Zeile 173):
  except OSError as e:

  # backup_zone (Zeile 207):
  except (hcloud.APIException, OSError) as e:
  ```

  Benötigte Imports: `import hcloud` (statt `from hcloud import Client`).

---

- [x] **3.3 – DNS-Resolver einmal in `__init__` anlegen** (`dnsjinja.py:139`)

  ```python
  # __init__ – einmalig anlegen (nach _prepare_zones, da name-servers aus config):
  self._resolver = dns.resolver.Resolver(configure=False)
  self._resolver.nameservers = self.config["global"]["name-servers"]

  # _get_zone_serial – gespeicherten Resolver nutzen:
  def _get_zone_serial(self, domain: str) -> str:
      try:
          r = self._resolver.resolve(domain, "SOA")
          return str(r[0].serial)
      except ...:
          ...
  ```

---

- [x] **3.4 – Erfolgsmeldung in `write_zone_files()` außerhalb des `with`-Blocks** (`dnsjinja.py:170–172`)

  Beide `print()`-Aufrufe sind aktuell gleich weit eingerückt, obwohl
  nur einer in die Datei schreibt. Den zweiten nach außen verschieben:

  ```python
  # vorher:
  with open(zonefile, 'w', encoding='utf-8') as zf:
      print(self.zones[domain], file=zf)
      print(f'Domäne {domain} wurde erfolgreich geschrieben')

  # nachher:
  with open(zonefile, 'w', encoding='utf-8') as zf:
      print(self.zones[domain], file=zf)
  print(f'Domäne {domain} wurde erfolgreich geschrieben')
  ```

---

- [x] **3.5 – Mindest-Versionen für Abhängigkeiten** (`setup.cfg`)

  ```ini
  install_requires =
      Jinja2>=3.0
      hcloud>=2.0
      dnspython>=2.3
      Click>=8.0
      python-dotenv>=1.0
      jsonschema>=4.0
      appdirs>=1.4
  ```

---

- [x] **3.6 – `$schema` auf HTTPS umstellen** (`dnsjinja_config_schema.py:2`)

  ```python
  # vorher:
  "$schema": "http://json-schema.org/draft-07/schema",
  # nachher:
  "$schema": "https://json-schema.org/draft-07/schema",
  ```

---

### Verbesserungsideen

- [x] **1.1 – Validierung der Zone-File-Syntax vor dem Upload** (`dnsjinja.py`)

  Gerenderte Zone-Files mit `dns.zone.from_text()` syntaktisch prüfen, bevor
  sie an die Hetzner API gesendet werden. Ungültige Zone-Files frühzeitig
  abfangen statt auf einen API-Fehler zu warten.

- [x] **1.2 – `_serials` korrekt typisieren** (`dnsjinja.py`)

  `self._serials: dict = {}` → `self._serials: dict[str, str] = {}` (Python 3.10+).

- [x] **1.3 – `--dry-run`-Flag** (`dnsjinja.py`)

  Zone-Files rendern und auf stdout ausgeben, ohne zu schreiben oder
  hochzuladen. Nützlich für CI-Pipelines und manuelle Kontrolle.

- [x] **1.4 – Template-Namen gegen Traversal absichern** (`dnsjinja.py`)

  Template-Namen aus der Config gegen ein Whitelist-Regex prüfen
  (`^[a-zA-Z0-9._-]+$`), bevor `env.get_template()` aufgerufen wird.

---

### Code-Vereinfachung (Abschnitt 1)

- [x] **1.1 – `_check_dir` / `_check_file` zusammenführen** (`dnsjinja.py:33–51`)
- [x] **1.2 – Redundantes `hetzner_domains`-Set entfernen** (`dnsjinja.py:57–72`)
- [x] **1.3 – `UploadError.msgfmt` – toter Code** (`dnsjinja.py:23–26`)
- [x] **1.4 – Unbenutzte Loop-Variable `d`** (`dnsjinja.py:234,255`)
- [x] **1.5 – Properties ohne Validierungslogik entfernen** (`dnsjinja.py:138–164`)

---

### Myloadenv – .env-Ladereihenfolge

- [x] **2.2 – Korrekte Kaskadenreihenfolge in `myloadenv.py`** (`myloadenv.py:33–37`)

  Die verschachtelte Schleife lädt alle gefundenen `.env`-Dateien ohne
  `break`; de-facto gewinnt die zuerst gefundene Datei (Home-Dir), nicht die
  spezifischste (CWD). Konventionelle Reihenfolge implementieren:
  CWD > User-Home-Dotdir > User-Config-Dir > `/etc` (Linux/Container).
  Gleichzeitig: `appdirs` → `platformdirs`, `Path().absolute()` → `Path.cwd()`.

---

### Bugs (Zweites Review)

- [x] **2.1 – `__main__.py` – fehlender `import sys`** (`__main__.py:5`)

  `sys` wird in `__main__.py` verwendet, aber nicht importiert.
  Jeder Aufruf via `python -m dnsjinja` endet mit `NameError`.

- [x] **2.2 – `explore_hetzner.py` – Token im Klartext sichtbar** (`explore_hetzner.py:13`)

  `input()` → `getpass.getpass()`, damit der Token beim Tippen
  nicht im Terminal erscheint.

- [x] **2.3 – `explore_hetzner.py` – Breites `except Exception`** (`explore_hetzner.py:25,30`)

  `except Exception` → `except hcloud.APIException` bzw. `except OSError`.

---

### Robustheit (Abschnitt 2 – Improvements.md)

- [x] **2.1 – `exit_on_error.py` – `int(ec)` ohne Fehlerbehandlung** (`exit_on_error.py:26`)

  `int(ec)` → `int(ec.strip())` mit `ValueError`-Abfang + `Path.read_text()` statt `open()`.

- [x] **2.3 – JSON-Schema: `additionalItems: True` entfernen** (`dnsjinja_config_schema.py:82`)

  Wirkungsloses Keyword bei `items`-Objekt gemäß JSON Schema Draft 7 entfernt.

- [x] **2.4 – JSON-Schema: `anyOf` mit einem Element vereinfachen** (`dnsjinja_config_schema.py:85–94`)

  `anyOf`-Wrapper mit einzelnem Element durch das direkte Schema-Objekt ersetzt.

---

### Wartbarkeit (Abschnitt 3 – Improvements.md)

- [x] **3.1 – Type Hints für `__init__`** (`dnsjinja.py:71`)

  Alle Parameter und Rückgabetyp annotiert: `bool`, `str`, `-> None`.

- [x] **3.2 – `__version__` und `__all__` in `__init__.py`** (`__init__.py`)

  `__version__ = '0.3.0'` und `__all__` ergänzt.

- [x] **3.3 – Testlücke: Schema-Validierung** (`test_unit.py`)

  Neuer Test `TestConfigValidierung.test_config_ohne_template_schlaegt_fehl`.

- [x] **3.4 – Testlücke: Template-Rendering** (`test_unit.py`)

  Neuer Test `TestZoneRendering.test_template_variablen_werden_substituiert`.

---

### Modernisierungspotenzial (Abschnitt 4 – Improvements.md)

- [x] **M.1 – `appdirs` → `platformdirs`** (`myloadenv.py:1,14`)

  Bereits umgesetzt: `import platformdirs` + `platformdirs.user_config_dir()`.

- [x] **M.2 – `Path().absolute()` → `Path.cwd()`** (`myloadenv.py:16`)

  Bereits umgesetzt: `cwd = Path.cwd()`.

- [x] **M.3 – `setup.cfg` → `pyproject.toml` (PEP 621)** (`setup.cfg`, `pyproject.toml`)

  Alle Metadaten, Dependencies und Entry-Points nach `pyproject.toml` migriert.
  `setup.cfg` entfernt. `jsonschema` durch `pydantic>=2.0` ersetzt.

- [x] **M.4 – `pathlib`-Methoden statt `open()`** (`exit_on_error.py:21–22`)

  Bereits umgesetzt als Teil von 2.1: `Path.read_text()` statt `with open()`.
  Zusätzlich in `dnsjinja.py`: `Path.write_text()` in `write_zone_files()`,
  `upload_zone()` und `backup_zone()`.

- [x] **M.5 – `print()` → `click.echo()`** (`dnsjinja.py`, `explore_hetzner.py`)

  Alle console-`print()`-Aufrufe durch `click.echo()` ersetzt.
  Fehlermeldungen in `explore_hetzner.py` mit `err=True`.

- [x] **M.6 – `logging`-Modul einrichten** (gesamte Codebasis)

  `import logging` + `logger = logging.getLogger(__name__)` in `dnsjinja.py`.
  `logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')`
  in `main()`. Kombination mit `click.echo()` für User-facing Output.

- [x] **M.7 – `jsonschema` → `pydantic` v2** (`dnsjinja_config_schema.py`, `dnsjinja.py`)

  `DNSJINJA_JSON_SCHEMA`-Dict durch Pydantic-Modelle (`DomainConfig`,
  `GlobalConfig`, `DnsJinjaConfig`) ersetzt. `jsonschema.validate()` durch
  `_DnsJinjaConfigModel.model_validate()` abgelöst.

- [x] **M.8 – Moderne Type-Annotation-Syntax (Python 3.10+)** (`dnsjinja.py`)

  `self._hetzner_zones: dict[str, Any]`, `self._create_missing: bool`,
  `_create_zone_data() -> dict[str, str]` annotiert. Kein `Optional`/`Dict`/`List`
  aus `typing` mehr.

- [x] **M.9 – `TypedDict` für Domain-Konfiguration** (`dnsjinja.py`)

  `DomainConfigEntry(TypedDict, total=False)` mit `template: Required[str]`,
  `zone_file: str`, `zone_id: str` eingeführt.