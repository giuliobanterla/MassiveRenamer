"""Crea l'eseguibile per il sistema su cui gira: MassiveRenamer.exe su Windows, MassiveRenamer.app su macOS.

Uso: python build.py   (risultato nella cartella dist/)
"""

import sys

import PyInstaller.__main__

args = ["run.py", "--name", "MassiveRenamer", "--windowed", "--noconfirm", "--clean"]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "info.gbss.massiverenamer"]
else:
    args += ["--onefile"]
PyInstaller.__main__.run(args)
