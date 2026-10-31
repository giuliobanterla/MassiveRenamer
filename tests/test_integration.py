import plistlib
import sys
import threading
import time
import uuid

import pytest

from massiverenamer import integration


def test_workflow_files(tmp_path):
    app = tmp_path / "My Apps" / "MassiveRenamer.app"
    files = integration.workflow_files(app, "Rinomina con MassiveRenamer")
    info = plistlib.loads(files["Contents/Info.plist"])
    service = info["NSServices"][0]
    assert service["NSMenuItem"]["default"] == "Rinomina con MassiveRenamer"
    assert service["NSMessage"] == "runWorkflowAsService"
    assert service["NSSendFileTypes"] == ["public.item"]
    document = plistlib.loads(files["Contents/document.wflow"])
    params = document["actions"][0]["action"]["ActionParameters"]
    assert params["COMMAND_STRING"] == f"open -a '{app}' \"$@\"\n"
    assert params["inputMethod"] == 1
    assert document["workflowMetaData"]["workflowTypeIdentifier"] == "com.apple.Automator.servicesMenu"


def test_mac_install_and_uninstall(tmp_path):
    app = tmp_path / "MassiveRenamer.app"
    integration.mac_install(app, "Rinomina", services=tmp_path)
    assert str(app) in integration.mac_installed_app(services=tmp_path)
    integration.mac_uninstall(services=tmp_path)
    assert integration.mac_installed_app(services=tmp_path) is None


@pytest.mark.skipif(sys.platform != "win32", reason="registro di Windows")
def test_windows_registry(tmp_path):
    base = rf"Software\MassiveRenamerTest-{uuid.uuid4().hex[:8]}\Classes"
    exe = tmp_path / "MassiveRenamer.exe"
    try:
        integration.win_install(exe, "Rinomina", base=base)
        assert integration.win_installed_command(base=base) == f'"{exe}" "%1"'
    finally:
        integration.win_uninstall(base=base)
        import winreg

        for key in (base, base.rsplit("\\", 1)[0]):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            except OSError:
                pass
    assert integration.win_installed_command(base=base) is None


def test_single_instance_forwards_paths(tmp_path, qapp):
    from massiverenamer.single_instance import SingleInstance

    app = qapp
    name = f"MassiveRenamerTest-{uuid.uuid4().hex[:8]}"
    first, second = SingleInstance(name), SingleInstance(name)
    received = []
    first.received.connect(received.extend)
    assert first.acquire()
    assert not second.acquire()
    # Il secondo avvio aspetta la conferma: nel test gira in un altro thread, mentre questo
    # fa girare gli eventi dell'istanza principale come farebbe la finestra aperta.
    result = []
    sender = threading.Thread(target=lambda: result.append(second.send([str(tmp_path / "a.txt"), str(tmp_path / "b c.txt")])))
    sender.start()
    deadline = time.monotonic() + 10
    while (sender.is_alive() or not received) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    sender.join(1)
    assert result == [True]
    assert received == [str(tmp_path / "a.txt"), str(tmp_path / "b c.txt")]
    first.lock.unlock()
