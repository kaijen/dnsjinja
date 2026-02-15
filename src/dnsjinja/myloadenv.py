import sys
from pathlib import Path
import dotenv
import platformdirs


def load_env(module_param: str | None = None) -> None:
    """Lädt .env-Konfigurationsdateien in konventioneller Kaskadenreihenfolge.

    Geladene Dateien (von höchster zu niedrigster Priorität):
      1. <CWD>/{module}.env  und  <CWD>/.env
      2. ~/.<module>/{module}.env  und  ~/.<module>/.env
      3. platformdirs.user_config_dir(module)/{module}.env  und  .env
         (Linux: ~/.config/{module}/,  Windows: %APPDATA%\\{module}\\)
      4. /etc/{module}/{module}.env  und  /etc/{module}/.env  (nur Linux/macOS)

    Bereits gesetzte Umgebungsvariablen (Shell, Container via -e) werden nie
    überschrieben (override=False). Innerhalb der Kaskade gewinnt die
    spezifischste Datei (CWD vor User-Config vor System).
    """
    module = module_param or Path(sys.argv[0]).stem
    home = Path.home()
    cwd = Path.cwd()
    user_conf = Path(platformdirs.user_config_dir(module, ''))

    # Verzeichnisse von höchster zu niedrigster Priorität
    dirs: list[Path] = [
        cwd,
        home / f'.{module}',
        user_conf,
    ]
    if sys.platform != 'win32':
        dirs.append(Path('/etc') / module)

    # Dateinamen von spezifisch zu generisch
    names = [f'{module}.env', '.env']

    # Kandidaten sammeln (Reihenfolge = Priorität hoch → niedrig)
    candidates = [d / n for d in dirs for n in names]

    for path in candidates:
        if path.is_file():
            dotenv.load_dotenv(path, override=False)
