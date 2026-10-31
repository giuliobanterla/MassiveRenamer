import json
import subprocess
from pathlib import Path

import pytest

import build


class FakeNotarytool:
    """Risponde come `xcrun notarytool`: `results` sono gli esiti in ordine (dict, oppure
    un'eccezione da sollevare, come un errore di rete)."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd[2])
        if cmd[2] == "log":
            return subprocess.CompletedProcess(cmd, 0, "registro di Apple", "")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return subprocess.CompletedProcess(cmd, 0, json.dumps(result), "")


def network_error():
    return subprocess.CalledProcessError(1, "notarytool", stderr="The Internet connection appears to be offline.")


def test_notarize_survives_network_errors():
    fake = FakeNotarytool([network_error(), {"id": "abc"}, {"status": "In Progress"}, network_error(),
                           network_error(), {"status": "Accepted"}])
    build.notarize(Path("x.dmg"), [], runner=fake, sleep=lambda s: None)
    assert fake.calls == ["submit", "submit", "info", "info", "info", "info"]


def test_notarize_invalid_prints_log(capsys):
    fake = FakeNotarytool([{"id": "abc"}, {"status": "Invalid"}])
    with pytest.raises(SystemExit, match="Invalid"):
        build.notarize(Path("x.dmg"), [], runner=fake, sleep=lambda s: None)
    assert "registro di Apple" in capsys.readouterr().out


def test_notarize_gives_up():
    fake = FakeNotarytool([{"id": "abc"}] + [network_error()] * 3)
    with pytest.raises(subprocess.CalledProcessError):
        build.notarize(Path("x.dmg"), [], runner=fake, sleep=lambda s: None, max_errors=3)
    fake = FakeNotarytool([{"id": "abc"}] + [{"status": "In Progress"}] * 5)
    with pytest.raises(SystemExit, match="ancora in corso"):
        build.notarize(Path("x.dmg"), [], runner=fake, sleep=lambda s: None, interval=10, timeout=30)
