#!/usr/bin/env python3

# pylint: disable=missing-module-docstring

import pathlib
import re
import sys

from setuptools import setup


HERE = pathlib.Path(__file__).absolute().parent
VERSION_FILE = HERE / 'omnisafe' / 'version.py'

sys.path.insert(0, str(VERSION_FILE.parent))
import version  # noqa


VERSION_CONTENT = None

try:
    if not version.__release__:
        try:
            VERSION_CONTENT = VERSION_FILE.read_text(encoding='UTF-8')
            VERSION_FILE.write_text(
                data=re.sub(
                    r"""__version__\s*=\s*('[^']+'|"[^"]+")""",
                    f"__version__ = '{version.__version__}'",
                    string=VERSION_CONTENT,
                ),
                encoding='UTF-8',
            )
        except OSError:
            VERSION_CONTENT = None

    setup(
        name='omnisafe',
        version=version.__version__,
        entry_points={'console_scripts': ['omnisafe=omnisafe:app']},
    )
finally:
    if VERSION_CONTENT is not None:
        with VERSION_FILE.open(mode='wt', encoding='UTF-8', newline='') as file:
            file.write(VERSION_CONTENT)
