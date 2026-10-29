"""Aggiornamento automatico dalle release GitHub del progetto.

Il controllo contatta solo l'API di GitHub e scarica solo dalle release di questo repository.
Il file scaricato deve corrispondere all'hash in SHA256SUMS.txt della stessa release.
Non dipende da Qt: l'interfaccia lo usa da un thread separato.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__

REPO = "giuliobanterla/MassiveRenamer"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
SUMS_NAME = "SHA256SUMS.txt"
CHECK_INTERVAL = 24 * 3600
TIMEOUT = 30

# Per provare un aggiornamento: l'app crede di essere questa versione.
PRETEND_ENV = "MASSIVERENAMER_PRETEND_VERSION"


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    notes: str
    page_url: str
    assets: dict[str, str] = field(default_factory=dict)  # nome → URL di download


def current_version() -> str:
    return os.environ.get(PRETEND_ENV) or __version__


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def asset_name(plat: str = sys.platform, machine: str | None = None) -> str | None:
    """Nome dell'eseguibile per questo sistema, come pubblicato da release.yml."""
    machine = (machine or platform.machine()).lower()
    if plat == "win32":
        return "MassiveRenamer-windows-x64.exe"
    if plat == "darwin":
        return f"MassiveRenamer-macos-{'arm64' if machine in ('arm64', 'aarch64') else 'x64'}.zip"
    return None


def _ssl_context() -> ssl.SSLContext:
    # Negli eseguibili PyInstaller i certificati di sistema non sempre si trovano: si usa certifi.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": f"MassiveRenamer/{__version__}"})
    return urllib.request.urlopen(request, timeout=TIMEOUT, context=_ssl_context())


def parse_release(data: dict) -> Release:
    version = str(data.get("tag_name", "")).lstrip("v")
    if parse_version(version) is None:
        raise UpdateError(f"versione non valida: {data.get('tag_name')!r}")
    assets = {
        a["name"]: a["browser_download_url"]
        for a in data.get("assets", [])
        if str(a.get("browser_download_url", "")).startswith(DOWNLOAD_PREFIX)
    }
    return Release(version, data.get("body") or "", data.get("html_url") or RELEASES_PAGE, assets)


def fetch_latest() -> Release | None:
    """La release pubblicata più recente, o None se non ce n'è ancora nessuna."""
    try:
        with _open(API_LATEST) as response:
            return parse_release(json.load(response))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(str(exc)) from exc
    except (OSError, ValueError, KeyError) as exc:
        raise UpdateError(str(exc)) from exc


def check() -> Release | None:
    """La release più recente se è più nuova di quella in uso, altrimenti None."""
    release = fetch_latest()
    return release if release and is_newer(release.version, current_version()) else None


def parse_sums(text: str) -> dict[str, str]:
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, progress: Callable[[int, int], None] | None = None) -> None:
    if not url.startswith(DOWNLOAD_PREFIX):
        raise UpdateError(f"indirizzo non ammesso: {url}")
    try:
        with _open(url) as response, dest.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except OSError as exc:
        raise UpdateError(str(exc)) from exc


def download_verified(release: Release, name: str, dest: Path,
                      progress: Callable[[int, int], None] | None = None) -> None:
    """Scarica l'eseguibile `name` e controlla l'hash con SHA256SUMS.txt della stessa release."""
    if name not in release.assets or SUMS_NAME not in release.assets:
        raise UpdateError(f"la release {release.version} non contiene {name} e {SUMS_NAME}")
    sums_path = dest.with_name(dest.name + ".sums")
    try:
        download(release.assets[SUMS_NAME], sums_path)
        expected = parse_sums(sums_path.read_text(encoding="utf-8", errors="replace")).get(name)
    finally:
        sums_path.unlink(missing_ok=True)
    if not expected:
        raise UpdateError(f"{name} non è elencato in {SUMS_NAME}")
    download(release.assets[name], dest, progress)
    actual = sha256_file(dest)
    if actual != expected:
        dest.unlink(missing_ok=True)
        raise UpdateError(f"hash diverso per {name}: atteso {expected}, ottenuto {actual}")


# --- Installazione --------------------------------------------------------------------------


def install_target(plat: str = sys.platform, executable: str = sys.executable,
                   frozen: bool | None = None) -> Path | None:
    """Cosa sostituire: l'.exe su Windows, la .app su macOS. None se l'app gira da sorgente
    o se la cartella non è scrivibile: in quel caso si può solo aprire la pagina della release."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        return None
    exe = Path(executable)
    if plat == "win32":
        target = exe
    elif plat == "darwin":
        target = exe.parents[2] if len(exe.parents) > 2 else exe
        if target.suffix != ".app":
            return None
    else:
        return None
    return target if os.access(target.parent, os.W_OK) else None


def old_path(exe: Path) -> Path:
    return exe.with_name(exe.name + ".old")


def cleanup_previous(plat: str = sys.platform) -> None:
    """All'avvio, toglie l'eseguibile della versione precedente lasciato da un aggiornamento su Windows."""
    target = install_target(plat)
    if plat == "win32" and target is not None:
        try:
            old_path(target).unlink(missing_ok=True)
        except OSError:
            pass


def swap_windows(exe: Path, new_exe: Path) -> None:
    """Windows permette di rinominare un .exe in esecuzione, non di sovrascriverlo:
    l'attuale diventa .old (cancellato al prossimo avvio) e il nuovo prende il suo nome."""
    old = old_path(exe)
    old.unlink(missing_ok=True)
    os.rename(exe, old)
    try:
        os.rename(new_exe, exe)
    except OSError:
        os.rename(old, exe)
        raise


def install_windows(release: Release, exe: Path, progress=None) -> None:
    new_exe = exe.with_name(f".{exe.stem}-{release.version}.exe")
    try:
        download_verified(release, asset_name("win32"), new_exe, progress)
        swap_windows(exe, new_exe)
    except OSError as exc:
        raise UpdateError(str(exc)) from exc
    finally:
        new_exe.unlink(missing_ok=True)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(exe)], creationflags=flags, close_fds=True)


def app_version(app: Path) -> str | None:
    import plistlib

    try:
        with (app / "Contents" / "Info.plist").open("rb") as f:
            return plistlib.load(f).get("CFBundleShortVersionString")
    except (OSError, ValueError):
        return None


def signing_team(app: Path) -> str | None:
    """Team ID del Developer ID che ha firmato la .app, o None (firma ad-hoc o assente)."""
    result = subprocess.run(["codesign", "-dv", str(app)], capture_output=True, text=True)
    m = re.search(r"^TeamIdentifier=(\w+)$", result.stderr, re.MULTILINE)
    return m.group(1) if result.returncode == 0 and m and m.group(1) != "not" else None


def verify_macos_signature(app: Path, team: str) -> None:
    """La nuova .app deve essere firmata dallo stesso team e accettata da Gatekeeper (notarizzata)."""
    requirement = f'=anchor apple generic and certificate leaf[subject.OU] = "{team}"'
    checks = (["codesign", "--verify", "--deep", "--strict", "-R", requirement, str(app)],
              ["spctl", "--assess", "--type", "execute", str(app)])
    for cmd in checks:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise UpdateError(f"firma non valida ({cmd[0]}): {result.stderr.strip()}")


def macos_swap_script(pid: int, app: Path, new_app: Path, work: Path) -> str:
    """Script che aspetta la chiusura dell'app, sostituisce la .app, rimette la vecchia se qualcosa
    va storto e apre quella nuova."""
    q = shlex.quote
    backup = work / "old.app"
    return f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
if mv {q(str(app))} {q(str(backup))}; then
  if mv {q(str(new_app))} {q(str(app))}; then
    open {q(str(app))}
    rm -rf {q(str(work))}
  else
    mv {q(str(backup))} {q(str(app))}
    open {q(str(app))}
  fi
fi
"""


def install_macos(release: Release, app: Path, progress=None) -> None:
    """Scarica e prepara la nuova .app; la sostituzione la fa uno script dopo la chiusura dell'app."""
    work = Path(tempfile.mkdtemp(prefix=".massiverenamer-update-", dir=app.parent))
    try:
        archive = work / "update.zip"
        download_verified(release, asset_name("darwin"), archive, progress)
        extracted = work / "new"
        subprocess.run(["ditto", "-x", "-k", str(archive), str(extracted)], check=True, capture_output=True)
        archive.unlink()
        new_app = extracted / "MassiveRenamer.app"
        found = app_version(new_app)
        if found != release.version:
            raise UpdateError(f"l'app scaricata ha versione {found!r} invece di {release.version}")
        # Un'app firmata accetta solo aggiornamenti firmati e notarizzati dallo stesso team.
        team = signing_team(app)
        if team:
            verify_macos_signature(new_app, team)
        script = work / "swap.sh"
        script.write_text(macos_swap_script(os.getpid(), app, new_app, work), encoding="utf-8")
    except UpdateError:
        shutil.rmtree(work, ignore_errors=True)
        raise
    except (OSError, subprocess.CalledProcessError) as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise UpdateError(str(exc)) from exc
    subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install(release: Release, progress=None) -> None:
    """Installa la release. Dopo il ritorno l'app deve chiudersi: su Windows la nuova versione
    è già partita, su macOS parte quando questa si chiude."""
    target = install_target()
    if target is None:
        raise UpdateError("questa installazione non si può aggiornare da sola")
    if sys.platform == "win32":
        install_windows(release, target, progress)
    else:
        install_macos(release, target, progress)


def due(settings: dict, now: float | None = None) -> bool:
    """Vero se il controllo automatico è attivo e l'ultimo è di più di un giorno fa."""
    upd = settings.get("updates", {})
    now = time.time() if now is None else now
    return upd.get("auto") is True and now - float(upd.get("last_check", 0)) >= CHECK_INTERVAL
