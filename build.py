"""Crea l'eseguibile per il sistema su cui gira: MassiveRenamer.exe su Windows, MassiveRenamer.app su macOS.

Uso: python build.py   (risultato nella cartella dist/)
"""

import plistlib
import sys
from pathlib import Path

import PyInstaller.__main__

from massiverenamer import __version__

args = ["run.py", "--name", "MassiveRenamer", "--windowed", "--noconfirm", "--clean"]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "info.gbss.massiverenamer"]
else:
    args += ["--onefile"]
PyInstaller.__main__.run(args)

if sys.platform == "darwin":
    # La versione nell'Info.plist serve all'aggiornamento automatico per controllare l'app scaricata.
    plist_path = Path("dist/MassiveRenamer.app/Contents/Info.plist")
    with plist_path.open("rb") as f:
        plist = plistlib.load(f)
    plist["CFBundleShortVersionString"] = plist["CFBundleVersion"] = __version__
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)
