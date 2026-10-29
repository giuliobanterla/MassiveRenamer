"""Parte grafica dell'aggiornamento automatico: barra in cima alla finestra e controllo in background."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget

from . import updater
from .i18n import tr


class UpdateBar(QFrame):
    """Barra con un messaggio e qualche pulsante; nascosta quando non c'è niente da dire."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("updateBar")
        self.setStyleSheet("#updateBar { background: palette(alternate-base); border-bottom: 1px solid palette(mid); }")
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(10, 6, 10, 6)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.hide()

    def show_message(self, text: str, buttons: list[tuple[str, object]]) -> None:
        while self.layout_.count():
            w = self.layout_.takeAt(0).widget()
            if w is not None and w is not self.label:
                w.deleteLater()
        self.label.setText(text)
        self.layout_.addWidget(self.label, 1)
        for caption, slot in buttons:
            b = QPushButton(caption)
            b.clicked.connect(slot)
            self.layout_.addWidget(b)
        self.show()


class UpdateController(QObject):
    """Decide quando controllare, mostra lo stato nella barra e installa.
    Sopravvive al cambio di lingua: la barra viene ricreata e `render()` la ridisegna."""

    _checked = Signal(object, object, bool)  # release o None, errore o None, controllo manuale
    _progress = Signal(int)
    _installed = Signal(object)  # None se riuscito, altrimenti il messaggio d'errore

    def __init__(self, window, settings: dict, save_settings):
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.save_settings = save_settings
        self.bar: UpdateBar | None = None
        self.state: tuple = ("hidden",)
        self.busy = False
        self._checked.connect(self._on_checked)
        self._progress.connect(self._on_progress)
        self._installed.connect(self._on_installed)

    @property
    def prefs(self) -> dict:
        return self.settings.setdefault("updates", {})

    @property
    def auto(self) -> bool:
        return self.prefs.get("auto") is True

    def set_auto(self, value: bool) -> None:
        self.prefs["auto"] = value
        self.save_settings(self.settings)

    def attach(self, bar: UpdateBar) -> None:
        self.bar = bar
        self.render()

    def start(self) -> None:
        updater.cleanup_previous()
        if self.prefs.get("auto") is None:
            self.state = ("consent",)
            self.render()
        elif updater.due(self.settings):
            self.check(manual=False)

    # --- Barra -----------------------------------------------------------------------------

    def render(self) -> None:
        if self.bar is None:
            return
        kind = self.state[0]
        if kind == "consent":
            self.bar.show_message(tr("upd_consent"), [(tr("upd_consent_yes"), lambda: self.answer_consent(True)),
                                                      (tr("upd_consent_no"), lambda: self.answer_consent(False))])
        elif kind == "available":
            release = self.state[1]
            can_install = updater.install_target() is not None
            buttons = [(tr("upd_install") if can_install else tr("upd_download"), self.install),
                       (tr("upd_notes"), lambda: self.open_url(release.page_url)),
                       (tr("upd_later"), self.dismiss)]
            self.bar.show_message(tr("upd_available", version=release.version,
                                     current=updater.current_version()), buttons)
        elif kind == "progress":
            self.bar.show_message(tr("upd_downloading", percent=self.state[1]), [])
        else:
            self.bar.hide()

    def dismiss(self) -> None:
        self.state = ("hidden",)
        self.render()

    def answer_consent(self, yes: bool) -> None:
        self.set_auto(yes)
        self.dismiss()
        if yes:
            self.check(manual=False)

    @staticmethod
    def open_url(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # --- Controllo -------------------------------------------------------------------------

    def check(self, manual: bool) -> None:
        if self.busy:
            return
        self.busy = True

        def run():
            try:
                self._checked.emit(updater.check(), None, manual)
            except updater.UpdateError as exc:
                self._checked.emit(None, str(exc), manual)

        threading.Thread(target=run, daemon=True).start()

    def _on_checked(self, release, error, manual: bool) -> None:
        self.busy = False
        if error is None:
            self.prefs["last_check"] = time.time()
            self.save_settings(self.settings)
        if release is not None:
            self.state = ("available", release)
            self.render()
        elif manual and error is not None:
            QMessageBox.warning(self.window, tr("upd_title"), tr("upd_check_failed", error=error))
        elif manual:
            QMessageBox.information(self.window, tr("upd_title"),
                                    tr("upd_up_to_date", version=updater.current_version()))

    # --- Installazione ---------------------------------------------------------------------

    def install(self) -> None:
        release = self.state[1]
        if updater.install_target() is None:
            self.open_url(release.page_url)
            return
        if self.busy:
            return
        self.busy = True
        self.state = ("progress", 0)
        self.render()

        def progress(done: int, total: int):
            if total:
                self._progress.emit(int(done * 100 / total))

        def run():
            try:
                updater.install(release, progress)
                self._installed.emit(None)
            except updater.UpdateError as exc:
                self._installed.emit(str(exc))

        self._release = release
        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, percent: int) -> None:
        if self.state[0] == "progress" and percent != self.state[1]:
            self.state = ("progress", percent)
            self.render()

    def _on_installed(self, error) -> None:
        self.busy = False
        if error is None:
            # Su Windows la nuova versione è già partita; su macOS parte quando questa si chiude.
            self.window.close()
            QApplication.quit()
            return
        self.state = ("available", self._release)
        self.render()
        QMessageBox.warning(self.window, tr("upd_title"), tr("upd_install_failed", error=error))
