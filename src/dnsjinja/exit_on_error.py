from pathlib import Path
import tempfile
import click
import sys

_POINTER_FILE = Path(tempfile.gettempdir()) / "dnsjinja.exit.ptr"


@click.command()
@click.option(
    '--exit-file', envvar='DNSJINJA_EXIT_FILE', default='',
    help="Pfad zur Exit-Code-Datei (DNSJINJA_EXIT_FILE). "
         "Wird nicht angegeben, liest exit_on_error den Pfad aus der Pointer-Datei."
)
def run(exit_file):
    if exit_file:
        exit_code_file = Path(exit_file)
    elif _POINTER_FILE.exists():
        exit_code_file = Path(_POINTER_FILE.read_text(encoding='utf-8').strip())
    else:
        sys.exit(0)

    if exit_code_file.exists():
        with open(exit_code_file, "r", encoding="utf8") as ecf:
            ec = ecf.read()
        sys.exit(int(ec))
    else:
        sys.exit(0)


if __name__ == '__main__':

    # Umgebungsvariablen noch bei Bedarf aus .env laden
    run()
