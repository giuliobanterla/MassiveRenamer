"""Voce «Rinomina con MassiveRenamer» nel menu del tasto destro.

- Windows: chiavi in HKEY_CURRENT_USER (nessun permesso da amministratore) per file, cartelle e
  sfondo di una cartella. Su Windows 11 compare sotto «Mostra altre opzioni».
- macOS: un'Azione rapida (servizio Automator) in ~/Library/Services, nel menu Azioni rapide del Finder.

Il comando punta all'eseguibile o alla .app in uso; se il programma viene spostato, `refresh()`
all'avvio aggiorna il percorso.
"""

from __future__ import annotations

import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


WIN_BASE = r"Software\Classes"
WIN_KEYS = {
    r"*\shell\MassiveRenamer": '"%1"',
    r"Directory\shell\MassiveRenamer": '"%1"',
    r"Directory\Background\shell\MassiveRenamer": '"%V"',
}
SERVICES_DIR = Path.home() / "Library" / "Services"
WORKFLOW_NAME = "MassiveRenamer.workflow"


def target() -> Path | None:
    """Il programma da lanciare: l'.exe su Windows, la .app su macOS. None se gira da sorgente."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable)
    if sys.platform == "win32":
        return exe
    if sys.platform == "darwin" and len(exe.parents) > 2 and exe.parents[2].suffix == ".app":
        return exe.parents[2]
    return None


def supported() -> bool:
    return target() is not None


# --- Windows --------------------------------------------------------------------------------


def _win_command(exe: Path, arg: str) -> str:
    return f'"{exe}" {arg}'


def win_install(exe: Path, label: str, base: str = WIN_BASE) -> None:
    import winreg

    for key, arg in WIN_KEYS.items():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{base}\\{key}") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, label)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
            # Senza questo Esplora risorse nasconde la voce quando si selezionano più di 15 file
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{base}\\{key}\\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, _win_command(exe, arg))


def win_uninstall(base: str = WIN_BASE) -> None:
    import winreg

    for key in WIN_KEYS:
        for sub in (f"{base}\\{key}\\command", f"{base}\\{key}"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass


def win_installed_command(base: str = WIN_BASE) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{base}\\{next(iter(WIN_KEYS))}\\command") as k:
            return winreg.QueryValueEx(k, None)[0]
    except OSError:
        return None


# --- macOS ----------------------------------------------------------------------------------


def workflow_files(app: Path, label: str) -> dict[str, bytes]:
    """Contenuto dell'Azione rapida: Info.plist e document.wflow (formato di Automator)."""
    script = f"open -a {shlex.quote(str(app))} \"$@\"\n"
    info = {
        "CFBundleName": label,
        "NSServices": [{
            "NSBackgroundColorName": "background",
            "NSIconName": "NSActionTemplate",
            "NSMenuItem": {"default": label},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": ["public.item"],
        }],
    }
    ids = [str(uuid.uuid4()).upper() for _ in range(3)]
    action = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {k: {} for k in ("COMMAND_STRING", "CheckedForUserDefaultShell",
                                                  "inputMethod", "shell", "source")},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": script,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,  # elementi passati come argomenti ("$@")
            "shell": "/bin/sh",
            "source": "",
        },
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": ids[0],
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": ids[1],
        "UUID": ids[2],
        "UnlocalizedApplications": ["Automator"],
        "arguments": {
            str(i): {"default value": default, "name": name, "required": "0", "type": "0", "uuid": str(i)}
            for i, (name, default) in enumerate((("inputMethod", 0), ("CheckedForUserDefaultShell", True),
                                                  ("source", ""), ("COMMAND_STRING", ""), ("shell", "")))
        },
        "isViewVisible": 1,
        "location": "309.000000:253.000000",
        "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
    }
    document = {
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{"action": action, "isViewVisible": 1}],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": 0,
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": 0,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": 0,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }
    return {"Contents/Info.plist": plistlib.dumps(info), "Contents/document.wflow": plistlib.dumps(document)}


def mac_install(app: Path, label: str, services: Path = SERVICES_DIR) -> None:
    workflow = services / WORKFLOW_NAME
    shutil.rmtree(workflow, ignore_errors=True)
    for name, data in workflow_files(app, label).items():
        path = workflow / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    _refresh_services()


def mac_uninstall(services: Path = SERVICES_DIR) -> None:
    shutil.rmtree(services / WORKFLOW_NAME, ignore_errors=True)
    _refresh_services()


def mac_installed_app(services: Path = SERVICES_DIR) -> str | None:
    """Il comando dell'Azione rapida installata, o None."""
    try:
        with (services / WORKFLOW_NAME / "Contents" / "document.wflow").open("rb") as f:
            return plistlib.load(f)["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
    except (OSError, ValueError, KeyError, IndexError):
        return None


def _refresh_services() -> None:
    # Fa rileggere subito i servizi al sistema; senza, la voce compare dopo qualche minuto
    pbs = Path("/System/Library/CoreServices/pbs")
    if pbs.exists():
        subprocess.run([str(pbs), "-update"], check=False, capture_output=True)


# --- Interfaccia comune ---------------------------------------------------------------------


def installed_command() -> str | None:
    if sys.platform == "win32":
        return win_installed_command()
    if sys.platform == "darwin":
        return mac_installed_app()
    return None


def is_installed() -> bool:
    return installed_command() is not None


def install(label: str) -> None:
    app = target()
    if app is None:
        raise OSError("disponibile solo nel programma installato, non da sorgente")
    if sys.platform == "win32":
        win_install(app, label)
    else:
        mac_install(app, label)


def uninstall() -> None:
    if sys.platform == "win32":
        win_uninstall()
    elif sys.platform == "darwin":
        mac_uninstall()


def refresh(label: str) -> None:
    """All'avvio: se la voce è installata ma punta a un altro percorso (programma spostato), la aggiorna."""
    app = target()
    command = installed_command()
    if app is not None and command is not None and str(app) not in command:
        try:
            install(label)
        except OSError:
            pass

