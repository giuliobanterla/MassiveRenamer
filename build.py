"""Crea il programma per il sistema su cui gira, nella cartella dist/:
- Windows: MassiveRenamer-setup.exe (installer, se c'è Inno Setup 6), MassiveRenamer-portable.exe
  e la cartella MassiveRenamer/ da cui è fatto l'installer;
- macOS: MassiveRenamer.app e MassiveRenamer.dmg (l'app da trascinare in Applicazioni).

Uso: python build.py

Su macOS la firma è ad-hoc (l'app parte, ma Gatekeeper avvisa al primo avvio). Con queste variabili
d'ambiente l'app è firmata con un Developer ID e, se ci sono anche le credenziali, notarizzata:
  MACOS_SIGN_IDENTITY   "Developer ID Application: Nome (TEAMID)", già nel portachiavi
  APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   notarizzazione (password specifica per app)
Su Windows ISCC.exe si cerca nel PATH, in INNO_SETUP o nella cartella d'installazione standard.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import PyInstaller.__main__

from massiverenamer import __version__

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP = DIST / "MassiveRenamer.app"
DMG = DIST / "MassiveRenamer.dmg"
ISS = ROOT / "packaging" / "windows" / "MassiveRenamer.iss"
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
    # Le opzioni (icona, file da escludere per alleggerire l'eseguibile) sono in packaging/MassiveRenamer.spec
    if sys.platform == "win32":
        os.environ["MASSIVERENAMER_VERSION_FILE"] = str(windows_version_file())
    PyInstaller.__main__.run([str(ROOT / "packaging" / "MassiveRenamer.spec"), "--noconfirm", "--clean",
                              "--distpath", str(DIST), "--workpath", str(ROOT / "build")])


def stamp_version() -> None:
    # La versione nell'Info.plist serve all'aggiornamento automatico per controllare l'app scaricata.
    plist_path = APP / "Contents" / "Info.plist"
    with plist_path.open("rb") as f:
        plist = plistlib.load(f)
    plist["CFBundleShortVersionString"] = plist["CFBundleVersion"] = __version__
    plist["NSHumanReadableCopyright"] = "GPL-3.0"
    # File e cartelle aperti con «Apri con», trascinati sull'icona o mandati dall'Azione rapida;
    # LSHandlerRank None: l'app non diventa mai quella predefinita per nessun tipo di file
    plist["CFBundleDocumentTypes"] = [{
        "CFBundleTypeName": "File e cartelle",
        "CFBundleTypeRole": "Viewer",
        "LSHandlerRank": "None",
        "LSItemContentTypes": ["public.item", "public.folder"],
    }]
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


def find_iscc() -> str | None:
    candidates = [os.environ.get("INNO_SETUP"), shutil.which("iscc")]
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            candidates.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def installer_windows() -> None:
    iscc = find_iscc()
    if not iscc:
        print("==> Installer non creato: manca Inno Setup 6 (https://jrsoftware.org/isdl.php)")
        return
    run(iscc, "/Qp", f"/DAppVersion={__version__}", f"/DSourceDir={DIST / 'MassiveRenamer'}",
        f"/DOutputDir={DIST}", str(ISS))
    print(f"==> Installer: {DIST / 'MassiveRenamer-setup.exe'}")


def dmg_macos() -> None:
    """Immagine disco con l'app e il collegamento ad Applicazioni, firmata come l'app."""
    DMG.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "MassiveRenamer"
        stage.mkdir()
        run("ditto", str(APP), str(stage / APP.name))
        (stage / "Applications").symlink_to("/Applications")
        cmd = ["hdiutil", "create", "-volname", "MassiveRenamer", "-srcfolder", str(stage),
               "-fs", "HFS+", "-format", "UDZO", "-ov", str(DMG)]
        for attempt in range(3):  # sui runner hdiutil a volte risponde «Resource busy»
            if subprocess.run(cmd).returncode == 0:
                break
        else:
            raise SystemExit("hdiutil non riesce a creare il .dmg")
    identity = os.environ.get("MACOS_SIGN_IDENTITY")
    if identity:
        run("codesign", "--force", "--sign", identity, "--timestamp", str(DMG))
    print(f"==> Immagine disco: {DMG}")


def notarize_macos() -> None:
    """Notarizza il .dmg: la notarizzazione copre anche l'app che contiene, e il ticket viene
    applicato a entrambi (lo zip per l'aggiornamento automatico si fa dopo, dall'app)."""
    creds = [os.environ.get(k) for k in ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_APP_PASSWORD")]
    if not os.environ.get("MACOS_SIGN_IDENTITY") or not all(creds):
        print("==> Non notarizzata (manca il Developer ID o le credenziali)")
        return
    apple_id, team_id, password = creds
    print("==> Notarizzazione")
    run("xcrun", "notarytool", "submit", str(DMG), "--apple-id", apple_id, "--team-id", team_id,
        "--password", password, "--wait")
    run("xcrun", "stapler", "staple", str(APP))
    run("xcrun", "stapler", "staple", str(DMG))
    run("spctl", "--assess", "--type", "execute", "--verbose=2", str(APP))
    run("spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "--verbose=2", str(DMG))


if __name__ == "__main__":
    pyinstaller()
    if sys.platform == "darwin":
        stamp_version()
        sign_macos()
        dmg_macos()
        notarize_macos()
    elif sys.platform == "win32":
        installer_windows()
