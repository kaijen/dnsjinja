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

## 1  Security

### 1.1  API-Token über `input()` – sichtbar im Terminal 🔴
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeilen 190, 214

```python
self.auth_api_token = input("Auth-API-Token: ")
```

`input()` zeigt die Eingabe im Terminal an und hinterlässt das Token im
Shell-Verlauf. Betrifft beide Methoden `upload_zones()` und `backup_zones()`.

**Empfehlung:** `getpass.getpass("Auth-API-Token: ")` verwenden. Das Modul ist
in der Python-Standardbibliothek enthalten und maskiert die Eingabe.

---

### 1.2  Vorhersehbarer Pfad der Exit-Code-Datei – TOCTOU 🟠
**Dateien:** `src/dnsjinja/dnsjinja.py` Z. 69, 182–183; `src/dnsjinja/exit_on_error.py` Z. 8–12

```python
self.exit_status_file = Path(tempfile.gettempdir()) / "dnsjinja.exit.txt"
```

Der Dateiname ist fest und vorhersehbar. In einem Mehrbenutzer-System kann
ein anderer Prozess die Datei zwischen Schreiben und Lesen manipulieren
(TOCTOU-Race-Condition). Außerdem überschreiben mehrere gleichzeitig laufende
`dnsjinja`-Prozesse denselben Status.

**Empfehlung:** Dateinamen mit PID einschließen (`dnsjinja.{os.getpid()}.exit.txt`)
oder `tempfile.NamedTemporaryFile(delete=False, mode=0o600)` nutzen.
`exit_on_error` muss dann den richtigen Pfad übergeben bekommen.

---

### 1.3  `http://` als API-Endpunkt erlaubt 🟠
**Datei:** `src/dnsjinja/dnsjinja_config_schema.py`, Zeile 71

```json
"pattern": "^https?://"
```

Das Schema lässt `http://` zu. Über einen unverschlüsselten Endpunkt würde
der Bearer-Token im Klartext übertragen (Man-in-the-Middle).

**Empfehlung:** Pattern auf `^https://` einschränken.

---

## 2  Bugs

### 2.1  Falsche Variable in Fehlermeldung – Dateiname statt Objekt 🔴
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeile 75 + 79

```python
with open(self.config_file, encoding='utf-8') as config_file:   # ← schattiert self.config_file
    self.config = json.load(config_file)
jsonschema.validate(self.config, self.config_schema)
except Exception as e:
    print(f'Konfigurationsdatei {config_file} konnte nicht korrekt gelesen werden …')
    #                             ^^^^^^^^^^^ ist hier der offene File-Handle,
    #                             nicht der Pfad! Gibt <_io.TextIOWrapper ...> aus.
```

Im `except`-Block ist `config_file` der geöffnete File-Handle (aus dem
`with`-Block), nicht der Dateipfad. Die Fehlermeldung zeigt damit
`<_io.TextIOWrapper name=…>` statt des lesbaren Pfades.

**Empfehlung:** Im `except` `self.config_file` verwenden; die `with`-Variable
umbenennen, z. B. `as cfg_fh`.

---

### 2.2  SOA-Seriennummer-Überlauf bei Suffix 99 🔴
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeile 152

```python
serial_suffix = f'{int(soa_serial[-2:])+1:02d}'
```

Ist der aktuelle Zähler `99`, ergibt `99 + 1 = 100`, was `:02d` auf `"100"`
formatiert – die Seriennummer wird dann 11 statt 10 Zeichen lang. Das BIND-Format
erlaubt maximal 32-Bit-Integer (max. `4294967295`), aber die Logik nimmt an,
dass die letzten zwei Stellen immer `00`–`99` sind.

**Empfehlung:** Grenzfall abfangen:
```python
serial_suffix = f'{min(int(soa_serial[-2:]) + 1, 99):02d}'
```
oder besser: eine Warnung ausgeben und ggf. `sys.exit(1)`, wenn bereits 99
Änderungen am selben Tag vorliegen.

---

### 2.3  Zwei verschiedene Seriennummern für Dateiinhalt und Dateiname 🔴
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeilen 161, 168

```python
# In _create_zone_data(): serial wird ins Zone-File gerendert
zones[domain] = template.render(…, soa_serial=self._new_zone_serial(domain), …)

# In write_zone_files(): serial wird für den Dateinamen abgefragt – erneut!
zonefile = self.zone_files_dir / Path(d['zone-file'] + f'.{self._new_zone_serial(domain)}')
```

`_new_zone_serial()` führt bei jedem Aufruf eine DNS-SOA-Abfrage durch. Ändert
sich die Zone zwischen den beiden Aufrufen (z. B. durch einen parallelen Upload
oder bei Mitternacht), stehen unterschiedliche Seriennummern im Dateiinhalt und
im Dateinamen.

**Empfehlung:** Das Ergebnis von `_create_zone_data()` enthält bereits die
gerenderte Seriennummer. Die `serials`-Map sollte beim Rendern mitgespeichert
und in `write_zone_files()` wiederverwendet werden. Alternativ: serials als
Instanzvariable `self._serials: dict[str, str]` cachen.

---

### 2.4  `_check_dir` prüft nicht, ob der Pfad ein Verzeichnis ist 🟠
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeile 31

```python
if not path_to_check.exists():
```

`exists()` ist `True` auch für reguläre Dateien. Wird versehentlich ein
Dateipfad statt eines Verzeichnisses konfiguriert, gibt es keinen frühen Fehler
– erst bei `open(zonefile, 'w')` oder `FileSystemLoader` tritt ein schwer
verständlicher Fehler auf.

**Empfehlung:** `is_dir()` verwenden:
```python
if not path_to_check.is_dir():
    print(f'{typ} {path_to_check} ist kein Verzeichnis.')
    sys.exit(1)
```
(Die Konfigurationsdatei selbst sollte mit `is_file()` geprüft werden.)

---

### 2.5  `patternProperties` im JSON-Schema falsch geschrieben 🟠
**Datei:** `src/dnsjinja/dnsjinja_config_schema.py`, Zeile 106

```python
"pattern_properties": {   # ← Unterstrich statt camelCase
```

Das korrekte JSON-Schema-Schlüsselwort ist `patternProperties` (camelCase).
Der Schlüssel `pattern_properties` (Unterstrich) wird von `jsonschema` ignoriert.
Damit greift das `"required": ["template"]` für einzelne Domain-Einträge
**niemals** – eine Domain-Konfiguration ohne `template`-Feld besteht die
Validierung, bricht aber später mit einem `KeyError` ab.

**Empfehlung:** `"pattern_properties"` → `"patternProperties"` umbenennen.

---

### 2.6  Interaktiv eingegebenes Token ignoriert `dns-api-base` 🟠
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeilen 191, 215

```python
self.client = Client(token=self.auth_api_token)  # kein api_endpoint!
```

Wenn der Token über `input()` nachgefragt wird, wird ein neuer Client
**ohne** `api_endpoint` erstellt. Der in `config.json` konfigurierte
`dns-api-base`-Wert wird damit ignoriert. Das ist inkonsistent mit dem
initial in `__init__` erstellten Client (Zeile 91).

**Empfehlung:**
```python
self.client = Client(token=self.auth_api_token, api_endpoint=api_base)
```
`api_base` dafür als Instanzvariable speichern.

---

### 2.7  `global exit_status` in `main()` – toter Code 🟡
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeile 237

```python
def main():
    global exit_status   # ← nicht definiert, nie gesetzt, nie gelesen
    load_env()
    run()
```

`exit_status` ist weder global definiert noch wird die Variable irgendwo
verwendet. Das `global`-Statement hat keine Wirkung und ist irreführend.

**Empfehlung:** Zeile entfernen.

---

### 2.8  `python-dotenv` doppelt in `setup.cfg` 🟡
**Datei:** `setup.cfg`, Zeilen 27 und 30

```ini
    python-dotenv
    …
    python-dotenv    # ← Duplikat
```

**Empfehlung:** Eines der beiden Vorkommen entfernen.

---

## 3  Code-Qualität

### 3.1  `input()` ohne Token-Prüfung vor API-Initialisierung 🟠
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeilen 89–91

Der `Client` wird in `__init__` mit einem möglicherweise leeren Token
initialisiert. Die ersten API-Aufrufe in `_prepare_zones()` laufen dann
bereits gegen die echte API. Der fehlende Token wird erst später in
`upload_zones()` und `backup_zones()` geprüft. Fehler aus
`_prepare_zones()` entstehen mit einem kryptischen Hetzner-Fehler statt
einer klaren Meldung.

**Empfehlung:** Wenn `--upload` oder `--backup` gesetzt ist und kein Token
vorliegt, früh abbrechen – idealerweise bevor `_prepare_zones()` aufgerufen
wird.

---

### 3.2  `except Exception` zu breit – maskiert Debugging-Informationen 🟡
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeilen 49, 61, 78, 144, 173, 207

Alle Fehlerbehandlungen fangen `Exception` als Sammelkategorie ab. Dadurch
werden z. B. `KeyboardInterrupt` (Python 2-Verhalten, in Python 3 abgeleitet
von `BaseException`, also hier kein Problem) und Programmfehler wie `KeyError`
oder `AttributeError` genauso behandelt wie erwartete Netzwerkfehler.

Schwieriger zu debuggen sind Fälle, bei denen ein Tippfehler im Code einen
`AttributeError` erzeugt und die Meldung lautet: „Zonen bei Hetzner konnten
nicht ermittelt werden: 'DNSJinja' object has no attribute 'xyz'".

**Empfehlung:** Spezifische Exception-Typen verwenden:
- Netzwerk/hcloud-Fehler: `hcloud.APIException`
- JSON-Fehler: `json.JSONDecodeError`
- Schema-Fehler: `jsonschema.ValidationError`
- DNS-Fehler: `dns.exception.DNSException`

---

### 3.3  DNS-Resolver wird bei jedem SOA-Aufruf neu instanziiert 🟡
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeile 139

```python
def _get_zone_serial(self, domain: str) -> str:
    hetzner_resolver = dns.resolver.Resolver(configure=False)
    hetzner_resolver.nameservers = self.config["global"]["name-servers"]
```

Für jede Domain und jeden `_new_zone_serial()`-Aufruf wird ein neuer Resolver
erzeugt und die Nameserver-Liste neu gesetzt. Bei N Domains und 2 Aufrufen
pro Domain (einmal in `_create_zone_data`, einmal in `write_zone_files`) sind
das 2N Resolver-Instanzen.

**Empfehlung:** Resolver einmalig in `__init__` als `self._resolver` anlegen.

---

### 3.4  `write_zone_files()` meldet Erfolg, bevor `print()` überhaupt schreibt 🟡
**Datei:** `src/dnsjinja/dnsjinja.py`, Zeilen 170–172

```python
with open(zonefile, 'w', encoding='utf-8') as zf:
    print(self.zones[domain], file=zf)
    print(f'Domäne {domain} wurde erfolgreich geschrieben')
    #     ↑ Diese Ausgabe geht auf stdout, nicht in zf –
    #       sie ist korrekt, aber die Einrückung täuscht darüber hinweg
```

Die Einrückung legt nahe, beide `print()`-Aufrufe schreiben in `zf`.
Tatsächlich schreibt nur der erste in die Datei; der zweite gibt auf
`stdout` aus. Das ist korrekt, aber irreführend.

**Empfehlung:** Erfolgsmeldung außerhalb des `with`-Blocks platzieren
(eine Zeile nach innen gerutscht).

---

### 3.5  Fehlende Versionsgrenzen für Abhängigkeiten 🟡
**Datei:** `setup.cfg`, Zeilen 22–30

Keine einzige Abhängigkeit hat eine Versionsschranke (`>=`, `<`). Breaking
Changes in `hcloud`, `Jinja2` oder `dnspython` können jederzeit das Werkzeug
unbemerkt beschädigen.

**Empfehlung:** Mindestversionen festlegen, z. B.:
```ini
Jinja2>=3.0
hcloud>=2.0
dnspython>=2.3
Click>=8.0
python-dotenv>=1.0
jsonschema>=4.0
appdirs>=1.4
```

---

### 3.6  `$schema`-URL im JSON-Schema ist HTTP statt HTTPS 🟡
**Datei:** `src/dnsjinja/dnsjinja_config_schema.py`, Zeile 2

```python
"$schema": "http://json-schema.org/draft-07/schema",
```

Das `$id`-Feld (Zeile 3) zeigt auf eine nicht existierende Domain
(`jendrian.eu`). Für `jsonschema` ist das funktional unkritisch (beide
Felder werden zur Validierung nicht aufgelöst), aber es ist Best Practice,
die offizielle HTTPS-URI `https://json-schema.org/draft-07/schema` zu
verwenden.

---

## 4  Verbesserungsideen

### 4.1  Validierung der Zone-File-Syntax vor dem Upload 🔵
Gerenderte Zone-Files werden nicht syntaktisch geprüft. Ein ungültiges
Zone-File wird hochgeladen und Hetzner liefert dann einen Fehler zurück.
`dnspython` hat einen Zone-Parser (`dns.zone.from_text()`), der vor dem
Upload aufgerufen werden könnte.

---

### 4.2  SOA-Serial im `_create_zone_data()`-Rückgabewert mitführen 🔵
Zur Behebung von Bug 2.3 bietet sich an, `_create_zone_data()` ein
`dict[str, tuple[str, str]]` (domain → (zonefile_content, serial)) zurückgeben
zu lassen. So ist die Serial für `write_zone_files()` und zukünftige
Verwendungen direkt verfügbar.

---

### 4.3  `--dry-run`-Flag 🔵
Vor einem Upload wäre eine Vorschau-Option nützlich: Zone-File rendern und
ausgeben, aber weder schreiben noch hochladen. Besonders hilfreich für CI-Pipelines,
die Pull-Requests validieren.

---

### 4.4  Template-Namen gegen Traversal absichern 🔵
`env.get_template(d["template"])` akzeptiert den Template-Namen direkt aus der
Config. Jinja2's `FileSystemLoader` verhindert Pfad-Traversal durch seine
Sandbox, aber ein explizites Whitelist-Pattern
(`^[a-zA-Z0-9._-]+\.tpl$` o. ä.) würde die Intention klarer ausdrücken.

---

## Zusammenfassung

| # | Schweregrad | Datei / Zeile | Kurzbeschreibung |
|---|-------------|---------------|-----------------|
| 1.1 | 🔴 | `dnsjinja.py:190,214` | Token über `input()` sichtbar im Terminal |
| 1.2 | 🟠 | `dnsjinja.py:69`, `exit_on_error.py:8` | Vorhersehbarer Tmp-Dateiname (TOCTOU) |
| 1.3 | 🟠 | `dnsjinja_config_schema.py:71` | `http://`-Endpunkt erlaubt |
| 2.1 | 🔴 | `dnsjinja.py:75,79` | `config_file`-Variable schattiert → Fehlermeldung zeigt File-Handle |
| 2.2 | 🔴 | `dnsjinja.py:152` | SOA-Serial-Überlauf bei Suffix 99 |
| 2.3 | 🔴 | `dnsjinja.py:161,168` | Dateiinhalt und Dateiname können verschiedene Serials haben |
| 2.4 | 🟠 | `dnsjinja.py:31` | `_check_dir` prüft nicht `is_dir()` |
| 2.5 | 🟠 | `dnsjinja_config_schema.py:106` | `pattern_properties` statt `patternProperties` → Schema-Validierung greift nicht |
| 2.6 | 🟠 | `dnsjinja.py:191,215` | Interaktiver Client ohne `api_endpoint` |
| 2.7 | 🟡 | `dnsjinja.py:237` | `global exit_status` – toter Code |
| 2.8 | 🟡 | `setup.cfg:30` | `python-dotenv` doppelt |
| 3.1 | 🟠 | `dnsjinja.py:89` | Leeres Token initialisiert Client vor Prüfung |
| 3.2 | 🟡 | `dnsjinja.py:49,61,78,144,173,207` | `except Exception` zu breit |
| 3.3 | 🟡 | `dnsjinja.py:139` | DNS-Resolver wird pro Aufruf neu erstellt |
| 3.4 | 🟡 | `dnsjinja.py:172` | Erfolgsmeldung irreführend eingerückt |
| 3.5 | 🟡 | `setup.cfg:22–30` | Keine Versionsgrenzen für Abhängigkeiten |
| 3.6 | 🟡 | `dnsjinja_config_schema.py:2` | `$schema` HTTP statt HTTPS |
