import hashlib
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from massiverenamer import i18n, updater
from massiverenamer.updater import Release, UpdateError

PREFIX = updater.DOWNLOAD_PREFIX + "v1.2.0/"


def test_versions():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("1.2.3-beta") is None
    assert updater.is_newer("0.2.0", "0.1.0")
    assert updater.is_newer("v0.10.0", "0.9.9")
    assert updater.is_newer("1.0.1", "1.0")
    assert not updater.is_newer("1.0", "1.0.0")
    assert not updater.is_newer("0.1.0", "0.2.0")
    assert not updater.is_newer("garbage", "0.1.0")


def test_pretend_version(monkeypatch):
    monkeypatch.setenv(updater.PRETEND_ENV, "0.0.1")
    assert updater.current_version() == "0.0.1"


def test_asset_names():
    assert updater.asset_name("win32", "AMD64") == "MassiveRenamer-windows-x64.exe"
    assert updater.asset_name("darwin", "arm64") == "MassiveRenamer-macos-arm64.zip"
    assert updater.asset_name("darwin", "x86_64") == "MassiveRenamer-macos-x64.zip"
    assert updater.asset_name("linux", "x86_64") is None
    assert updater.asset_name("win32", "AMD64", installed=True) == "MassiveRenamer-setup-windows-x64.exe"


def test_windows_installed(tmp_path):
    exe = tmp_path / "MassiveRenamer.exe"
    exe.write_bytes(b"MZ")
    assert not updater.windows_installed(exe)  # versione portatile
    (tmp_path / "unins000.exe").write_bytes(b"MZ")
    assert updater.windows_installed(exe)  # messa dall'installer


def test_windows_setup_script():
    script = updater.windows_setup_script(1234, Path("C:/Temp/it's/MassiveRenamer-setup-1.0.exe"))
    assert script.startswith("Wait-Process -Id 1234 ")
    assert "'/VERYSILENT'" in script and "'/LAUNCH'" in script
    assert "it''s" in script  # apice raddoppiato nelle stringhe PowerShell


def test_parse_release_keeps_only_project_assets():
    data = {
        "tag_name": "v1.2.0",
        "body": "note",
        "html_url": "https://github.com/x",
        "assets": [
            {"name": "SHA256SUMS.txt", "browser_download_url": PREFIX + "SHA256SUMS.txt"},
            {"name": "evil.exe", "browser_download_url": "https://example.com/evil.exe"},
        ],
    }
    r = updater.parse_release(data)
    assert r.version == "1.2.0" and list(r.assets) == ["SHA256SUMS.txt"]
    with pytest.raises(UpdateError):
        updater.parse_release({"tag_name": "latest"})


def test_parse_sums():
    h = "a" * 64
    sums = updater.parse_sums(f"{h}  MassiveRenamer-windows-x64.exe\n{h} *other.zip\nnot a line\n")
    assert sums == {"MassiveRenamer-windows-x64.exe": h, "other.zip": h}


def test_download_rejects_foreign_urls(tmp_path):
    with pytest.raises(UpdateError):
        updater.download("https://example.com/file", tmp_path / "f")


def fake_downloads(monkeypatch, files: dict[str, bytes]):
    def fake(url, dest, progress=None):
        dest.write_bytes(files[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(updater, "download", fake)


def test_download_verified(monkeypatch, tmp_path):
    payload = b"new version"
    sums = f"{hashlib.sha256(payload).hexdigest()}  app.exe\n".encode()
    release = Release("1.2.0", "", "", {n: PREFIX + n for n in ("app.exe", "SHA256SUMS.txt")})

    fake_downloads(monkeypatch, {"app.exe": payload, "SHA256SUMS.txt": sums})
    updater.download_verified(release, "app.exe", tmp_path / "out.exe")
    assert (tmp_path / "out.exe").read_bytes() == payload

    fake_downloads(monkeypatch, {"app.exe": b"tampered", "SHA256SUMS.txt": sums})
    with pytest.raises(UpdateError):
        updater.download_verified(release, "app.exe", tmp_path / "bad.exe")
    assert not (tmp_path / "bad.exe").exists()

    with pytest.raises(UpdateError):
        updater.download_verified(Release("1.2.0", "", "", {}), "app.exe", tmp_path / "x")


def test_install_target(tmp_path):
    app = tmp_path / "MassiveRenamer.app"
    exe = app / "Contents" / "MacOS" / "MassiveRenamer"
    assert updater.install_target("darwin", str(exe), frozen=False) is None
    assert updater.install_target("darwin", str(exe), frozen=True) == app
    assert updater.install_target("darwin", str(tmp_path / "a" / "b" / "c" / "python"), frozen=True) is None
    assert updater.install_target("win32", str(tmp_path / "M.exe"), frozen=True) == tmp_path / "M.exe"
    assert updater.install_target("linux", "/usr/bin/x", frozen=True) is None


def test_swap_windows(tmp_path):
    exe, new = tmp_path / "MassiveRenamer.exe", tmp_path / ".new.exe"
    exe.write_text("old")
    new.write_text("new")
    updater.swap_windows(exe, new)
    assert exe.read_text() == "new" and updater.old_path(exe).read_text() == "old" and not new.exists()

    # Se il nuovo file manca, l'eseguibile attuale torna al suo posto.
    with pytest.raises(OSError):
        updater.swap_windows(exe, tmp_path / "missing.exe")
    assert exe.read_text() == "new"


def test_due():
    assert not updater.due({})
    assert not updater.due({"updates": {"auto": False}})
    assert updater.due({"updates": {"auto": True}})
    assert not updater.due({"updates": {"auto": True, "last_check": 1000}}, now=1000 + 3600)
    assert updater.due({"updates": {"auto": True, "last_check": 1000}}, now=1000 + 25 * 3600)


def make_app(path: Path, version: str) -> Path:
    (path / "Contents").mkdir(parents=True)
    with (path / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleShortVersionString": version}, f)
    return path


def test_app_version(tmp_path):
    assert updater.app_version(make_app(tmp_path / "A.app", "1.2.0")) == "1.2.0"
    assert updater.app_version(tmp_path / "missing.app") is None


@pytest.mark.skipif(sys.platform == "win32", reason="script sh")
def test_macos_swap_script(tmp_path, monkeypatch):
    app = make_app(tmp_path / "MassiveRenamer.app", "0.1.0")
    work = tmp_path / ".work"
    new_app = make_app(work / "new" / "MassiveRenamer.app", "0.2.0")
    script = updater.macos_swap_script(999999, app, new_app, work)
    # "open" non deve aprire davvero l'app durante il test.
    script = script.replace("open ", "echo opened ")
    result = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True)
    assert "opened" in result.stdout
    assert updater.app_version(app) == "0.2.0"
    assert not work.exists()


def test_translations_complete():
    assert set(i18n.STRINGS["it"]) == set(i18n.STRINGS["en"])
    for key, text in i18n.STRINGS["it"].items():
        placeholders = lambda s: sorted(re.findall(r"\{(\w+)\}", s))
        assert placeholders(text) == placeholders(i18n.STRINGS["en"][key]), key


@pytest.mark.skipif(sys.platform != "darwin", reason="codesign")
def test_macos_signature_checks(tmp_path):
    app = make_app(tmp_path / "Unsigned.app", "1.0.0")
    assert updater.signing_team(app) is None
    with pytest.raises(UpdateError):
        updater.verify_macos_signature(app, "D3694MQ8D9")
