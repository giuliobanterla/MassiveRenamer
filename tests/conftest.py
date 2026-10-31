"""Configurazione comune: l'interfaccia gira senza schermo (piattaforma Qt "offscreen")."""

import os

import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    # Senza schermo Qt cerca i font nella propria cartella, vuota su Windows: le immagini avrebbero solo quadratini
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Una sola QApplication per tutti i test (Qt non ne permette due)."""
    from massiverenamer.gui import Application

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or Application([])
    yield app
