"""Crea l'eseguibile per il sistema su cui gira: MassiveRenamer.exe su Windows, MassiveRenamer.app su macOS.

Uso: python build.py   (risultato nella cartella dist/)

Su macOS la firma è ad-hoc (l'app parte, ma Gatekeeper avvisa al primo avvio). Con queste variabili
d'ambiente l'app è firmata con un Developer ID e, se ci sono anche le credenziali, notarizzata:
  MACOS_SIGN_IDENTITY   "Developer ID Application: Nome (TEAMID)", già nel portachiavi
  APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   notarizzazione (password specifica per app)
"""

import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

import PyInstaller.__main__

from massiverenamer import __version__

ROOT = Path(__file__).resolve().parent
APP = ROOT / "dist" / "MassiveRenamer.app"
ENTITLEMENTS = ROOT / "packaging" / "macos" / "entitlements.plist"


def windows_version_file() -> Path:
    """Risorsa di versione dell'.exe: nome del prodotto e versione nelle proprietà del file."""
    nums = (tuple(int(p) for p in __version__.split(".")) + (0, 0, 0, 0))[:4]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[
    StringFileInfo([StringTable('041004B0', [
      StringStruct('CompanyName', 'Giulio Banterla'),
      StringStruct('FileDescription', 'MassiveRenamer'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'MassiveRenamer'),
      StringStruct('LegalCopyright', 'GPL-3.0'),
      StringStruct('OriginalFilename', 'MassiveRenamer.exe'),
      StringStruct('ProductName', 'MassiveRenamer'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x0410, 1200])])
  ]
)
"""
    path = Path(tempfile.gettempdir()) / "massiverenamer-version.txt"
    path.write_text(text, encoding="utf-8")
    return path


def pyinstaller() -> None:
    args = ["run.py", "--name", "MassiveRenamer", "--windowed", "--noconfirm", "--clean",
            "--add-data", f"massiverenamer/resources{os.pathsep}massiverenamer/resources"]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "info.gbss.massiverenamer", "--icon", "assets/icon/icon.icns"]
    else:
        args += ["--onefile", "--icon", "assets/icon/icon.ico", "--version-file", str(windows_version_file())]
    PyInstaller.__main__.run(args)


def stamp_version() -> None:
    # La versione nell'Info.plist serve all'aggiornamento automatico per controllare l'app scaricata.
    plist_path = APP / "Contents" / "Info.plist"
    with plist_path.open("rb") as f:
        plist = plistlib.load(f)
    plist["CFBundleShortVersionString"] = plist["CFBundleVersion"] = __version__
    plist["NSHumanReadableCopyright"] = "GPL-3.0"
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)


def run(*cmd: str) -> None:
    subprocess.run(cmd, check=True)


def is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
    except OSError:
        return False


def sign_macos() -> None:
    """Firma dall'interno verso l'esterno: librerie, framework, eseguibile, bundle.
    Va fatta dopo aver modificato l'Info.plist, che altrimenti invaliderebbe la firma."""
    identity = os.environ.get("MACOS_SIGN_IDENTITY") or "-"

    def sign(path: Path, entitlements: bool = False) -> None:
        cmd = ["codesign", "--force", "--sign", identity]
        if identity != "-":
            cmd += ["--options", "runtime", "--timestamp"]
        if entitlements:
            cmd += ["--entitlements", str(ENTITLEMENTS)]
        run(*cmd, str(path))

    main_exe = APP / "Contents" / "MacOS" / "MassiveRenamer"
    files = [p for p in APP.rglob("*") if p.is_file() and not p.is_symlink() and p != main_exe and is_macho(p)]
    for path in sorted(files, key=lambda p: len(p.parts), reverse=True):
        sign(path)
    frameworks = [p for p in APP.rglob("*.framework") if p.is_dir() and not p.is_symlink()]
    for path in sorted(frameworks, key=lambda p: len(p.parts), reverse=True):
        sign(path)
    sign(main_exe, entitlements=True)
    sign(APP, entitlements=True)
    run("codesign", "--verify", "--deep", "--strict", "--verbose=2", str(APP))
    print(f"==> Firmata con: {identity if identity != '-' else 'firma ad-hoc'}")


def notarize_macos() -> None:
    creds = [os.environ.get(k) for k in ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_APP_PASSWORD")]
    if not os.environ.get("MACOS_SIGN_IDENTITY") or not all(creds):
        print("==> Non notarizzata (manca il Developer ID o le credenziali)")
        return
    apple_id, team_id, password = creds
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "MassiveRenamer.zip"
        run("ditto", "-c", "-k", "--keepParent", str(APP), str(archive))
        print("==> Notarizzazione")
        run("xcrun", "notarytool", "submit", str(archive), "--apple-id", apple_id, "--team-id", team_id,
            "--password", password, "--wait")
    run("xcrun", "stapler", "staple", str(APP))
    run("spctl", "--assess", "--type", "execute", "--verbose=2", str(APP))


if __name__ == "__main__":
    pyinstaller()
    if sys.platform == "darwin":
        stamp_version()
        sign_macos()
        notarize_macos()
