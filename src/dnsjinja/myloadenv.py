import appdirs
import dotenv
import sys
from pathlib import Path


def load_env(module_param=None):
    if module_param:
        module = module_param
    else:
        module = Path(sys.argv[0]).stem
    dotmodule = '.' + module
    home = Path.home()
    userconfig = Path(appdirs.user_config_dir(module,''))
    dotconfig = Path('.config')
    dot = Path().absolute()

    env_paths = [
        home,
        userconfig,
        home / dotconfig,
        home / dotmodule,
        home / dotconfig / dotmodule,
        userconfig / module,
        dot
    ]

    env_names = [
        '.env',
        module + '.env'
    ]

    for p in env_paths:
        for n in env_names:
            file = Path(p) / Path(n)
            if file.exists():
                dotenv.load_dotenv(file)
