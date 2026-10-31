"""Configurazione comune: l'interfaccia gira senza schermo (piattaforma Qt "offscreen")."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Una sola QApplication per tutti i test (Qt non ne permette due)."""
    from massiverenamer.gui import Application

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or Application([])
    yield app
