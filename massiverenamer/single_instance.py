"""Una sola finestra per utente: un secondo avvio passa i suoi file a quella già aperta.

Serve soprattutto su Windows, dove Esplora risorse lancia un processo per ogni file selezionato
con il tasto destro. Il primo processo che prende il lock diventa l'istanza principale e ascolta
su un socket locale; gli altri le mandano i percorsi e si chiudono.
"""

from __future__ import annotations

import getpass
import json
import os
import time
from pathlib import Path

from PySide6.QtCore import QDir, QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def _name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - in casi rari getuser non trova l'utente
        user = "user"
    return f"MassiveRenamer-{''.join(c for c in user if c.isalnum()) or 'user'}"


class SingleInstance(QObject):
    received = Signal(list)  # percorsi arrivati da un altro avvio

    def __init__(self, name: str | None = None):
        super().__init__()
        self.name = name or _name()
        self.lock = QLockFile(os.path.join(QDir.tempPath(), f"{self.name}.lock"))
        self.lock.setStaleLockTime(0)
        self.server: QLocalServer | None = None

    def acquire(self) -> bool:
        """Vero se questa è l'istanza principale (e allora ascolta gli altri avvii)."""
        if not self.lock.tryLock(0):
            return False
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(self.name)
        return True

    def send(self, paths: list[str], timeout: float = 5.0) -> bool:
        """Manda i percorsi all'istanza principale, aspettando che sia pronta (può essere appena partita)."""
        data = json.dumps([str(Path(p).absolute()) for p in paths]).encode("utf-8")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                socket.write(data)
                socket.flush()
                socket.waitForBytesWritten(2000)
                socket.disconnectFromServer()
                return True
            time.sleep(0.1)
        return False

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            buffer = bytearray()

            def read(socket=socket, buffer=buffer):
                buffer.extend(bytes(socket.readAll()))

            def done(socket=socket, buffer=buffer):
                read()
                try:
                    paths = json.loads(buffer.decode("utf-8"))
                except ValueError:
                    paths = []
                if isinstance(paths, list):
                    self.received.emit([str(p) for p in paths])
                socket.deleteLater()

            socket.readyRead.connect(read)
            socket.disconnected.connect(done)
