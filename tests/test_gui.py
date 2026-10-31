"""Test dell'interfaccia senza schermo: finestra vera, dialoghi sostituiti da risposte fisse.

Le immagini della finestra finiscono in tests/screenshots/ (caricate come artifact dalla CI)."""

import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from massiverenamer import gui, i18n, updater
from massiverenamer.engine import Rules, Status

SCREENSHOTS = Path(__file__).parent / "screenshots"


@pytest.fixture
def dialogs(monkeypatch):
    """Registra i messaggi mostrati e risponde Sì alle domande; i file da scegliere si impostano qui."""
    shown = {"messages": [], "save": None, "open": None}

    def message(kind):
        return lambda parent, title, text, *a, **k: shown["messages"].append((kind, text))

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(message(kind)))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (shown["save"] or "", "")))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (shown["open"] or "", "")))
    return shown


@pytest.fixture
def window(qapp, tmp_path, monkeypatch, dialogs):
    """Finestra in italiano con impostazioni e annullamento in una cartella temporanea."""
    monkeypatch.setattr(gui, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(gui, "JOURNAL_FILE", tmp_path / "last_rename.json")
    i18n.set_language("it")
    w = gui.MainWindow({"updates": {"auto": False}}, [])
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    yield w
    w.preview_timer.stop()
    w.rescan_timer.stop()
    w.hide()
    w.deleteLater()
    qapp.processEvents()


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "foto"
    (d / "sub").mkdir(parents=True)
    for name in ("IMG_0012.JPG", "IMG_0003.JPG", "vacanze mare.jpeg", "note.txt", "sub/IMG_9.jpg", ".nascosto.jpg"):
        (d / name).write_text(name)
    return d


def wait(qapp, ms=500):
    QTest.qWait(ms)
    qapp.processEvents()


def names(w):
    return [p.name for p in w.paths]


def screenshot(w, name):
    SCREENSHOTS.mkdir(exist_ok=True)
    w.grab().save(str(SCREENSHOTS / f"{name}.png"))


def test_window_in_both_languages(window, qapp, folder):
    window.add_paths([folder])
    window.set_rules(Rules(prefix="2026 ", numbering=True, num_padding=3))
    wait(qapp)
    screenshot(window, "finestra-it")
    window.change_language("en")
    wait(qapp)
    assert window.btn_rename.text() == "Rename"
    assert window.get_rules().prefix == "2026 "  # regole e lista sopravvivono al cambio di lingua
    assert len(window.paths) == 4
    screenshot(window, "finestra-en")


def test_list_follows_filter_and_options(window, qapp, folder):
    window.add_paths([folder])
    wait(qapp)
    assert names(window) == ["IMG_0003.JPG", "IMG_0012.JPG", "note.txt", "vacanze mare.jpeg"]

    window.e_filter.setText("*.jpg;*.jpeg")
    wait(qapp)
    assert "note.txt" not in names(window)
    window.c_recursive.setChecked(True)
    wait(qapp)
    assert "IMG_9.jpg" in names(window)
    window.c_hidden.setChecked(True)
    wait(qapp)
    assert ".nascosto.jpg" in names(window)

    # Un file tolto a mano resta fuori anche cambiando filtro, finché non si riaggiunge la cartella
    window.table.selectRow(0)
    removed = names(window)[0]
    window.remove_selected()
    window.e_filter.setText("")
    wait(qapp)
    assert removed not in names(window)
    window.add_paths([folder])
    wait(qapp)
    assert removed in names(window)


def test_clear_list_button_and_shortcut(window, qapp, folder):
    window.add_paths([folder])
    wait(qapp)
    window.btn_clear.click()
    assert window.paths == [] and window.sources == []

    window.add_paths([folder])
    wait(qapp)
    assert window.paths
    assert window.act_clear.shortcuts()
    window.act_clear.trigger()
    assert window.paths == []


def test_typed_numbers_are_used(window, qapp, folder):
    window.add_paths([folder / "note.txt"])
    spin = window.s_trim_left
    spin.setFocus()
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), "2")
    wait(qapp)
    assert window.plan[0].new_name == "te.txt"
    # Anche senza aspettare l'anteprima, il valore scritto viene riletto prima di rinominare
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), "3")
    assert window.get_rules().trim_left == 3


def test_rules_round_trip(window):
    rules = Rules(
        replace_all=True, replace_all_text="x", find="a", replace_with="b", match_case=True, use_regex=True,
        replacements=[["c", "d"], ["e", ""]], remove_pos=2, remove_count=3, remove_from_end=True,
        trim_left=1, trim_right=2, insert_text="-", insert_pos=4, insert_from_end=True, case="title",
        prefix="p", suffix="s", date_mode="taken", date_format="%Y", date_position="after", date_separator=" ",
        numbering=True, num_start=5, num_step=2, num_padding=4, num_position="before", num_separator=".",
        ext_mode="replace", ext_text="png",
    )
    window.set_rules(rules)
    assert window.get_rules() == rules


def test_rename_and_undo(window, qapp, folder, dialogs):
    window.add_paths([folder])
    window.set_rules(Rules(find="IMG_", replace_with="Foto ", case="lower"))
    wait(qapp)
    # note.txt e "vacanze mare.jpeg" sono già minuscoli: restano invariati
    assert [i.status for i in window.plan].count(Status.OK) == 2
    window.do_rename()
    assert sorted(p.name for p in folder.iterdir() if p.is_file()) == [
        ".nascosto.jpg", "foto 0003.JPG", "foto 0012.JPG", "note.txt", "vacanze mare.jpeg"]
    assert names(window)[0].startswith("foto ")  # la lista segue i nuovi nomi
    assert dialogs["messages"][-1] == ("information", i18n.tr("done", count=2))

    window.do_undo()
    assert (folder / "IMG_0012.JPG").exists() and (folder / "note.txt").exists()
    assert not gui.JOURNAL_FILE.exists()


def test_rename_reports_problems(window, qapp, folder):
    window.add_paths([folder / "IMG_0003.JPG", folder / "IMG_0012.JPG"])
    window.set_rules(Rules(replace_all=True, replace_all_text="uguale"))
    wait(qapp)
    assert [i.status for i in window.plan] == [Status.DUPLICATE, Status.DUPLICATE]
    assert not window.btn_rename.isEnabled()


def test_export_scripts(window, qapp, folder, tmp_path, dialogs):
    window.add_paths([folder / "note.txt"])
    window.set_rules(Rules(prefix="x_"))
    wait(qapp)
    ext = "bat" if os.name == "nt" else "sh"
    dialogs["save"] = str(tmp_path / f"rinomina.{ext}")
    window.export_script()
    assert (tmp_path / f"rinomina.{ext}").exists()
    assert (tmp_path / f"rinomina-annulla.{ext}").exists()


def test_presets(window, qapp, tmp_path, dialogs):
    window.set_rules(Rules(prefix="salvata", replacements=[["a", "b"]]))
    window.e_filter.setText("*.png")
    dialogs["save"] = str(tmp_path / "regole")
    window.save_preset()
    data = json.loads((tmp_path / "regole.json").read_text(encoding="utf-8"))
    assert data["rules"]["prefix"] == "salvata" and data["files"]["filter"] == "*.png"

    window.set_rules(Rules())
    window.e_filter.setText("")
    dialogs["open"] = str(tmp_path / "regole.json")
    window.load_preset()
    assert window.get_rules().replacements == [["a", "b"]]
    assert window.e_filter.text() == "*.png"

    (tmp_path / "rotto.json").write_text("non json")
    dialogs["open"] = str(tmp_path / "rotto.json")
    window.load_preset()
    assert dialogs["messages"][-1] == ("critical", i18n.tr("preset_error"))


def test_update_bar(window, qapp):
    controller = window.updates
    window.settings["updates"] = {}
    controller.start()
    assert controller.state == ("consent",) and window.updates.bar.isVisible()
    controller.answer_consent(False)
    assert window.settings["updates"]["auto"] is False and not controller.bar.isVisible()

    # Da sorgente non si può installare: la barra offre di scaricare
    controller.state = ("available", updater.Release("9.9.9", "", "https://example.com", {}))
    controller.render()
    wait(qapp, 100)
    buttons = [b.text() for b in controller.bar.findChildren(type(window.btn_rename)) if b.isVisible()]
    assert i18n.tr("upd_download") in buttons
    screenshot(window, "barra-aggiornamento")


def test_context_menu_only_when_installed(window):
    assert not window.act_context.isEnabled()  # da sorgente
    assert window.act_context.toolTip() == i18n.tr("context_unsupported")


def test_path_bar(window, qapp, folder, tmp_path):
    assert window.e_path.isEnabled() and window.e_path.text() == ""
    assert window.e_path.completer() is None  # niente lettura dei dischi all'avvio
    window.add_paths([folder])
    wait(qapp)
    assert window.e_path.text() == str(folder)

    # Scrivendo un'altra cartella la lista diventa il suo contenuto
    other = tmp_path / "altra"
    other.mkdir()
    (other / "uno.txt").write_text("1")
    window.e_path.setFocus()
    window.e_path.selectAll()
    QTest.keyClicks(window.e_path, str(other))
    QTest.keyClick(window.e_path, Qt.Key_Return)
    wait(qapp)
    assert names(window) == ["uno.txt"] and window.e_path.text() == str(other)
    assert window.e_path.completer() is not None  # creato alla prima digitazione

    # Una cartella che non esiste viene segnalata e la lista non cambia
    window.e_path.selectAll()
    QTest.keyClicks(window.e_path, str(tmp_path / "manca"))
    QTest.keyClick(window.e_path, Qt.Key_Return)
    assert names(window) == ["uno.txt"]
    assert window.e_path.toolTip() == i18n.tr("path_invalid")

    # Con file da più cartelle la barra si disattiva
    window.table.setFocus()
    window.add_paths([folder])
    wait(qapp)
    assert not window.e_path.isEnabled()
    screenshot(window, "piu-cartelle")
    window.clear_list()
    assert window.e_path.isEnabled()


def test_manual_order(window, qapp, folder):
    window.add_paths([folder])
    window.set_rules(Rules(numbering=True, num_position="replace"))
    wait(qapp)
    first = names(window)[0]
    window.table.selectRow(0)
    window.act_move_down.trigger()
    assert names(window)[1] == first
    assert window.cb_sort.currentData() == "manual"
    assert window.plan[1].source.name == first and window.plan[1].new_name.startswith("2")
    window.act_move_up.trigger()
    assert names(window)[0] == first

    # Il filtro ricalcola la lista ma l'ordine manuale resta
    window.table.selectRow(0)
    window.act_move_down.trigger()
    order = names(window)
    window.c_hidden.setChecked(True)
    wait(qapp)
    assert [n for n in names(window) if n in order] == order


def test_highlight_spans():
    assert gui.changed_spans("IMG_0003.JPG", "Foto 0003.JPG") == [("Foto ", True), ("0003.JPG", False)]
    assert gui.changed_spans("a.txt", "a.txt") == [("a.txt", False)]


def test_undo_several_renames(window, qapp, folder):
    window.add_paths([folder / "note.txt"])
    window.set_rules(Rules(prefix="1_"))
    wait(qapp)
    window.do_rename()
    window.set_rules(Rules(prefix="2_"))
    wait(qapp)
    window.do_rename()
    assert (folder / "2_1_note.txt").exists()
    window.do_undo()
    assert (folder / "1_note.txt").exists()
    window.do_undo()
    assert (folder / "note.txt").exists()
    assert not window.act_undo.isEnabled()


def test_recent_presets(window, qapp, tmp_path, dialogs):
    window.set_rules(Rules(prefix="recente"))
    dialogs["save"] = str(tmp_path / "mie regole")
    window.save_preset()
    window.set_rules(Rules())
    window._fill_recent_menu()
    entries = [a for a in window.m_recent.actions() if a.text() == "mie regole"]
    assert entries
    entries[0].trigger()
    assert window.get_rules().prefix == "recente"

    (tmp_path / "mie regole.json").unlink()
    window.load_preset(str(tmp_path / "mie regole.json"))
    assert window.settings["recent_presets"] == []
    window._fill_recent_menu()
    assert not window.m_recent.actions()[0].isEnabled()  # "Nessuna regola recente"
