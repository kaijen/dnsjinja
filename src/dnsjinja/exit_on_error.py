from pathlib import Path
import tempfile
import click
import sys

@click.command()
def run():
    exit_code_file = Path(tempfile.gettempdir()) / "dnsjinja.exit.txt"
    if exit_code_file.exists():
        with open(exit_code_file, "r", encoding="utf8") as ecf:
            ec = ecf.read()
        sys.exit(int(ec))
    else:
        sys.exit(0)

if __name__ == '__main__':

    # Umgebungsvariablen noch bei Bedarf aus .env laden
    run()
