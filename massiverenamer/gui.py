"""Interfaccia grafica Qt (PySide6): regole a sinistra, anteprima a destra."""

from __future__ import annotations

import difflib
import html
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QDir, QEvent, QItemSelectionModel, QModelIndex, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QIcon, QKeySequence, QPalette, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileSystemModel,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import DONATE_URL, __version__, engine
from .engine import PlanItem, Rules, Status
from .i18n import LANGUAGES, current_language, default_language, set_language, tr
from . import integration
from .single_instance import SingleInstance
from .update_ui import UpdateBar, UpdateController

SETTINGS_FILE = engine.config_dir() / "settings.json"
JOURNAL_FILE = engine.config_dir() / "last_rename.json"

STATUS_COLORS = {
    Status.OK: QColor("#1a7f37"),
    Status.UNCHANGED: QColor("#808080"),
}
PROBLEM_COLOR = QColor("#cf222e")


def debug_log(message: str) -> None:
    """Registro di diagnostica, attivo solo se MASSIVERENAMER_DEBUG_LOG indica un file."""
    path = os.environ.get("MASSIVERENAMER_DEBUG_LOG")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except OSError:
            pass


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


class PlanModel(QAbstractTableModel):
    """Modello della tabella di anteprima: regge senza problemi decine di migliaia di righe."""

    COLUMNS = ("col_old", "col_new", "col_status", "col_folder")

    def __init__(self):
        super().__init__()
        self.plan: list[PlanItem] = []

    def set_plan(self, plan: list[PlanItem]) -> None:
        self.beginResetModel()
        self.plan = plan
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.plan)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return tr(self.COLUMNS[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        item = self.plan[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            if col == 0:
                return item.source.name
            if col == 1:
                return item.new_name
            if col == 2:
                text = tr(f"st_{item.status.value}")
                if item.message:
                    detail = tr(item.message) if item.status == Status.INVALID else item.message
                    text += f" ({detail})"
                return text
            if col == 3:
                return str(item.source.parent)
        if role == Qt.ForegroundRole and col in (1, 2):
            return STATUS_COLORS.get(item.status, PROBLEM_COLOR)
        return None


def changed_spans(old: str, new: str) -> list[tuple[str, bool]]:
    """Il nuovo nome diviso in pezzi, ognuno con True se è cambiato rispetto al vecchio."""
    spans: list[tuple[str, bool]] = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if j2 > j1:
            spans.append((new[j1:j2], tag != "equal"))
    return spans


class DiffDelegate(QStyledItemDelegate):
    """Colonna «Nuovo nome»: le parti cambiate rispetto al nome attuale sono evidenziate."""

    HIGHLIGHT = QColor(250, 204, 21, 110)

    def paint(self, painter, option, index):
        item = index.model().plan[index.row()]
        if item.status == Status.UNCHANGED:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        selected = bool(opt.state & QStyle.State_Selected)
        color = opt.palette.color(QPalette.HighlightedText) if selected else index.data(Qt.ForegroundRole)
        opt.text = ""
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        parts = []
        for text, changed in changed_spans(item.source.name, item.new_name):
            text = html.escape(text).replace(" ", "&nbsp;")
            parts.append(f'<span style="background-color:{self.HIGHLIGHT.name(QColor.HexArgb)}">{text}</span>'
                         if changed else text)
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(opt.font)
        doc.setHtml(f'<span style="color:{QColor(color).name()}; white-space:pre">{"".join(parts)}</span>')
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)
        painter.save()
        painter.setClipRect(rect)
        painter.translate(rect.left() + 2, rect.top() + (rect.height() - doc.size().height()) / 2)
        doc.drawContents(painter, QRectF(0, 0, rect.width(), rect.height()))
        painter.restore()


class MainWindow(QMainWindow):
    def __init__(self, settings: dict, initial_paths: list[str]):
        super().__init__()
        self.settings = settings
        self.paths: list[Path] = []
        self.sources: list[Path] = []  # file e cartelle aggiunti dall'utente
        self.excluded: set[str] = set()  # file tolti a mano dalla lista
        self.plan: list[PlanItem] = []
        self.model = PlanModel()
        self.preview_timer = QTimer(self, singleShot=True, interval=150)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.rescan_timer = QTimer(self, singleShot=True, interval=400)
        self.rescan_timer.timeout.connect(self.rebuild_list)
        self.updates = UpdateController(self, settings, save_settings)

        self.setAcceptDrops(True)
        self.resize(1200, 760)
        self._build_ui()
        self.set_rules(Rules.from_dict(settings.get("rules", {})))
        self.file_options_from_settings()
        self.add_paths([Path(p) for p in initial_paths])
        self.refresh_preview()

    # --- Costruzione dell'interfaccia ------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(tr("app_title"))
        self.menuBar().clear()
        for tb in self.findChildren(QToolBar):
            self.removeToolBar(tb)
            tb.deleteLater()

        def action(key, slot, shortcut=None):
            a = QAction(tr(key), self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(shortcut)
            return a

        self.act_add_files = action("add_files", self.choose_files, QKeySequence.Open)
        self.act_add_folder = action("add_folder", self.choose_folder)
        self.act_remove = action("remove", self.remove_selected, QKeySequence.Delete)
        self.act_clear = action("clear", self.clear_list)
        self.act_clear.setShortcuts([QKeySequence("Ctrl+Shift+Backspace"), QKeySequence("Ctrl+Shift+Delete")])
        self.act_move_up = action("move_up", lambda: self.move_selected(-1), "Alt+Up")
        self.act_move_down = action("move_down", lambda: self.move_selected(1), "Alt+Down")
        self.act_rename = action("rename", self.do_rename, "Ctrl+R")
        self.act_undo = action("undo", self.do_undo, QKeySequence.Undo)
        self.act_export = action("export_script", self.export_script)
        self.act_load = action("load_preset", self.load_preset)
        self.act_save = action("save_preset", self.save_preset)
        self.act_reset = action("reset_rules", lambda: self.set_rules(Rules()))
        self.act_context = QAction(tr("context_menu"), self, checkable=True)
        self.act_context.setEnabled(integration.supported())
        self.act_context.setChecked(integration.is_installed())
        self.act_context.toggled.connect(self.toggle_context_menu)
        if not integration.supported():
            self.act_context.setToolTip(tr("context_unsupported"))
        act_quit = action("quit", self.close, QKeySequence.Quit)
        act_quit.setMenuRole(QAction.QuitRole)
        act_about = action("about", self.show_about)
        act_about.setMenuRole(QAction.AboutRole)
        act_donate = action("donate", self.open_donate)
        act_check = action("upd_check_now", lambda: self.updates.check(manual=True))
        act_check.setMenuRole(QAction.ApplicationSpecificRole)
        act_auto = QAction(tr("upd_auto"), self, checkable=True, checked=self.updates.auto)
        act_auto.toggled.connect(self.updates.set_auto)

        m_file = self.menuBar().addMenu(tr("menu_file"))
        for a in (self.act_add_files, self.act_add_folder, None, self.act_load):
            m_file.addSeparator() if a is None else m_file.addAction(a)
        self.m_recent = m_file.addMenu(tr("recent_presets"))
        self.m_recent.aboutToShow.connect(self._fill_recent_menu)
        for a in (self.act_save, None, self.act_export, None, self.act_context, None, act_quit):
            m_file.addSeparator() if a is None else m_file.addAction(a)
        m_edit = self.menuBar().addMenu(tr("menu_edit"))
        for a in (self.act_rename, self.act_undo, None, self.act_move_up, self.act_move_down, None,
                  self.act_remove, self.act_clear, None, self.act_reset):
            m_edit.addSeparator() if a is None else m_edit.addAction(a)
        m_lang = self.menuBar().addMenu(tr("language"))
        group = QActionGroup(self)
        for code, label in LANGUAGES.items():
            a = QAction(label, self, checkable=True, checked=code == current_language())
            a.triggered.connect(lambda _=False, c=code: self.change_language(c))
            group.addAction(a)
            m_lang.addAction(a)
        m_help = self.menuBar().addMenu(tr("menu_help"))
        for a in (act_check, act_auto, None, act_donate, act_about):
            m_help.addSeparator() if a is None else m_help.addAction(a)

        tb = QToolBar(self, movable=False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for a in (self.act_add_files, self.act_add_folder, self.act_remove, self.act_clear, None,
                  self.act_undo, self.act_export):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(tb)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_rules_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 800])
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = UpdateBar()
        layout.addWidget(bar)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.updates.attach(bar)

    def _changed(self, *_):
        self.preview_timer.start()

    def _line(self) -> QLineEdit:
        w = QLineEdit()
        w.textChanged.connect(self._changed)
        return w

    def _spin(self, minimum: int, maximum: int) -> QSpinBox:
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setKeyboardTracking(True)
        # Il valore scritto a mano deve contare subito, non solo dopo le frecce
        w.valueChanged.connect(self._changed)
        w.lineEdit().textEdited.connect(self._changed)
        w.editingFinished.connect(self._changed)
        self._spins.append(w)
        return w

    def _check(self, key: str) -> QCheckBox:
        w = QCheckBox(tr(key))
        w.toggled.connect(self._changed)
        return w

    def _combo(self, prefix: str, codes: tuple[str, ...]) -> QComboBox:
        w = QComboBox()
        for code in codes:
            w.addItem(tr(f"{prefix}_{code}"), code)
        w.currentIndexChanged.connect(self._changed)
        return w

    def _group(self, key: str, checkable: bool = False) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(tr(key))
        if checkable:
            box.setCheckable(True)
            box.toggled.connect(self._changed)
        form = QFormLayout(box)
        return box, form

    def _build_rules_panel(self) -> QWidget:
        self._spins: list[QSpinBox] = []
        inner = QWidget()
        layout = QVBoxLayout(inner)

        box, form = self._group("grp_replace_all", checkable=True)
        self.g_replace_all = box
        self.e_replace_all = self._line()
        form.addRow(tr("replace_all_text"), self.e_replace_all)
        layout.addWidget(box)

        box, form = self._group("grp_find")
        self.e_find, self.e_replace = self._line(), self._line()
        self.c_match_case, self.c_regex = self._check("match_case"), self._check("use_regex")
        form.addRow(tr("find"), self.e_find)
        form.addRow(tr("replace_with"), self.e_replace)
        row = QHBoxLayout()
        row.addWidget(self.c_match_case)
        row.addWidget(self.c_regex)
        form.addRow(row)
        self.t_replacements = QTableWidget(0, 2)
        self.t_replacements.setHorizontalHeaderLabels([tr("find").rstrip(":"), tr("replace_with").rstrip(":")])
        self.t_replacements.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.t_replacements.verticalHeader().hide()
        self.t_replacements.setMaximumHeight(110)
        self.t_replacements.itemChanged.connect(self._changed)
        add_row, del_row = QPushButton(tr("add_row")), QPushButton(tr("remove_row"))
        add_row.clicked.connect(lambda: self._add_replacement_row("", ""))
        del_row.clicked.connect(self._remove_replacement_row)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("more_replacements")), 1)
        row.addWidget(add_row)
        row.addWidget(del_row)
        form.addRow(row)
        form.addRow(self.t_replacements)
        layout.addWidget(box)

        box, form = self._group("grp_remove")
        self.s_remove_pos, self.s_remove_count = self._spin(1, 255), self._spin(0, 255)
        self.c_remove_end = self._check("from_end")
        row = QHBoxLayout()
        for label, w in (("remove_pos", self.s_remove_pos), ("remove_count", self.s_remove_count)):
            row.addWidget(QLabel(tr(label)))
            row.addWidget(w)
        form.addRow(row)
        form.addRow(self.c_remove_end)
        layout.addWidget(box)

        box, form = self._group("grp_trim")
        self.s_trim_left, self.s_trim_right = self._spin(0, 255), self._spin(0, 255)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("trim_left")))
        row.addWidget(self.s_trim_left)
        row.addWidget(QLabel(tr("trim_right")))
        row.addWidget(self.s_trim_right)
        form.addRow(row)
        layout.addWidget(box)

        box, form = self._group("grp_insert_at")
        self.e_insert_text = self._line()
        self.s_insert_pos = self._spin(0, 255)
        self.c_insert_end = self._check("from_end")
        form.addRow(tr("insert_text"), self.e_insert_text)
        row = QHBoxLayout()
        row.addWidget(self.s_insert_pos)
        row.addWidget(self.c_insert_end, 1)
        form.addRow(tr("insert_pos"), row)
        layout.addWidget(box)

        box, form = self._group("grp_case")
        self.cb_case = self._combo("case", engine.CASE_MODES)
        form.addRow(self.cb_case)
        layout.addWidget(box)

        box, form = self._group("grp_insert")
        self.e_prefix, self.e_suffix = self._line(), self._line()
        form.addRow(tr("prefix"), self.e_prefix)
        form.addRow(tr("suffix"), self.e_suffix)
        layout.addWidget(box)

        box, form = self._group("grp_date")
        self.cb_date = self._combo("date", engine.DATE_MODES)
        self.e_date_format = self._line()
        self.e_date_format.setToolTip(tr("date_format_help"))
        self.cb_date_position = self._combo("pos", engine.NUM_POSITIONS)
        self.e_date_sep = self._line()
        self.e_date_sep.setMaximumWidth(60)
        form.addRow(self.cb_date)
        form.addRow(tr("date_format"), self.e_date_format)
        row = QHBoxLayout()
        row.addWidget(self.cb_date_position, 1)
        row.addWidget(QLabel(tr("num_separator")))
        row.addWidget(self.e_date_sep)
        form.addRow(tr("num_position"), row)
        self.cb_date.currentIndexChanged.connect(self._update_date_fields)
        layout.addWidget(box)

        box, form = self._group("grp_numbering", checkable=True)
        self.g_numbering = box
        self.s_num_start, self.s_num_step = self._spin(-999999, 999999), self._spin(-9999, 9999)
        self.s_num_padding = self._spin(1, 12)
        self.cb_num_position = self._combo("pos", engine.NUM_POSITIONS)
        self.e_num_sep = self._line()
        self.e_num_sep.setMaximumWidth(60)
        row = QHBoxLayout()
        for label, w in (("num_start", self.s_num_start), ("num_step", self.s_num_step), ("num_padding", self.s_num_padding)):
            row.addWidget(QLabel(tr(label)))
            row.addWidget(w)
        form.addRow(row)
        form.addRow(tr("num_position"), self.cb_num_position)
        form.addRow(tr("num_separator"), self.e_num_sep)
        layout.addWidget(box)

        box, form = self._group("grp_ext")
        self.cb_ext = self._combo("ext", engine.EXT_MODES)
        self.e_ext = self._line()
        self.cb_ext.currentIndexChanged.connect(
            lambda: self.e_ext.setEnabled(self.cb_ext.currentData() == "replace"))
        row = QHBoxLayout()
        row.addWidget(self.cb_ext)
        row.addWidget(self.e_ext)
        form.addRow(row)
        layout.addWidget(box)

        box, form = self._group("grp_files")
        self.e_filter = QLineEdit(placeholderText=tr("filter_placeholder"))
        self.c_recursive = QCheckBox(tr("recursive"))
        self.c_hidden = QCheckBox(tr("hidden"))
        # Filtro e opzioni valgono anche per i file già in lista: si ricalcola la lista
        self.e_filter.textChanged.connect(lambda: self.rescan_timer.start())
        self.c_recursive.toggled.connect(self.rebuild_list)
        self.c_hidden.toggled.connect(self.rebuild_list)
        self.cb_sort = QComboBox()
        for code in engine.SORT_KEYS:
            self.cb_sort.addItem(tr(f"sort_{code}"), code)
        self.c_reverse = QCheckBox(tr("sort_reverse"))
        self.cb_sort.currentIndexChanged.connect(self.resort)
        self.c_reverse.toggled.connect(self.resort)
        form.addRow(tr("filter"), self.e_filter)
        form.addRow(self.c_recursive)
        form.addRow(self.c_hidden)
        form.addRow(tr("sort_by"), self.cb_sort)
        form.addRow(self.c_reverse)
        layout.addWidget(box)

        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(inner.sizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 4)
        return scroll

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Cartella dei file in lista: si può scrivere a mano per passare a un'altra cartella
        path_row = QHBoxLayout()
        self.e_path = QLineEdit()
        self.e_path.setClearButtonEnabled(True)
        dirs = QFileSystemModel(self.e_path)
        dirs.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)
        dirs.setRootPath("")
        completer = QCompleter(dirs, self.e_path)
        completer.setCaseSensitivity(Qt.CaseInsensitive if sys.platform in ("win32", "darwin") else Qt.CaseSensitive)
        self.e_path.setCompleter(completer)
        self.e_path.returnPressed.connect(self.open_typed_path)
        self.e_path.textEdited.connect(lambda: self._set_path_error(False))
        path_row.addWidget(QLabel(tr("path_label")))
        path_row.addWidget(self.e_path, 1)
        layout.addLayout(path_row)

        self.table = QTableView()
        self.table.setItemDelegateForColumn(1, DiffDelegate(self.table))
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(22)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for col, width in enumerate((260, 260, 150)):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.lbl_summary = QLabel()
        self.btn_rename = QPushButton(tr("rename"))
        self.btn_rename.setDefault(True)
        self.btn_rename.setMinimumWidth(140)
        self.btn_rename.clicked.connect(self.do_rename)
        self.btn_clear = QPushButton(tr("clear"))
        self.btn_clear.setToolTip(self.act_clear.shortcut().toString(QKeySequence.NativeText))
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_up, self.btn_down = QPushButton("↑"), QPushButton("↓")
        for button, act in ((self.btn_up, self.act_move_up), (self.btn_down, self.act_move_down)):
            button.setToolTip(f"{act.text()} ({act.shortcut().toString(QKeySequence.NativeText)})")
            button.setMaximumWidth(40)
            button.clicked.connect(act.trigger)
        bottom.addWidget(self.lbl_summary, 1)
        bottom.addWidget(self.btn_up)
        bottom.addWidget(self.btn_down)
        bottom.addWidget(self.btn_clear)
        bottom.addWidget(self.btn_rename)
        layout.addLayout(bottom)
        return panel

    # --- Regole ----------------------------------------------------------------------------

    def _add_replacement_row(self, find: str, replace: str) -> None:
        row = self.t_replacements.rowCount()
        self.t_replacements.insertRow(row)
        self.t_replacements.setItem(row, 0, QTableWidgetItem(find))
        self.t_replacements.setItem(row, 1, QTableWidgetItem(replace))
        if not find:
            self.t_replacements.editItem(self.t_replacements.item(row, 0))

    def _remove_replacement_row(self) -> None:
        rows = sorted({i.row() for i in self.t_replacements.selectedIndexes()} or {self.t_replacements.rowCount() - 1})
        for row in reversed(rows):
            if row >= 0:
                self.t_replacements.removeRow(row)
        self._changed()

    def _replacement_pairs(self) -> list[list[str]]:
        pairs = []
        for row in range(self.t_replacements.rowCount()):
            cells = [self.t_replacements.item(row, c) for c in (0, 1)]
            find, replace = (c.text() if c else "" for c in cells)
            if find:
                pairs.append([find, replace])
        return pairs

    def _update_date_fields(self) -> None:
        on = self.cb_date.currentData() != "none"
        for w in (self.e_date_format, self.cb_date_position, self.e_date_sep):
            w.setEnabled(on)

    def get_rules(self) -> Rules:
        for spin in self._spins:
            spin.interpretText()
        return Rules(
            replace_all=self.g_replace_all.isChecked(),
            replace_all_text=self.e_replace_all.text(),
            find=self.e_find.text(),
            replace_with=self.e_replace.text(),
            match_case=self.c_match_case.isChecked(),
            use_regex=self.c_regex.isChecked(),
            replacements=self._replacement_pairs(),
            remove_pos=self.s_remove_pos.value(),
            remove_count=self.s_remove_count.value(),
            remove_from_end=self.c_remove_end.isChecked(),
            trim_left=self.s_trim_left.value(),
            trim_right=self.s_trim_right.value(),
            insert_text=self.e_insert_text.text(),
            insert_pos=self.s_insert_pos.value(),
            insert_from_end=self.c_insert_end.isChecked(),
            case=self.cb_case.currentData(),
            prefix=self.e_prefix.text(),
            suffix=self.e_suffix.text(),
            date_mode=self.cb_date.currentData(),
            date_format=self.e_date_format.text(),
            date_position=self.cb_date_position.currentData(),
            date_separator=self.e_date_sep.text(),
            numbering=self.g_numbering.isChecked(),
            num_start=self.s_num_start.value(),
            num_step=self.s_num_step.value(),
            num_padding=self.s_num_padding.value(),
            num_position=self.cb_num_position.currentData(),
            num_separator=self.e_num_sep.text(),
            ext_mode=self.cb_ext.currentData(),
            ext_text=self.e_ext.text(),
        )

    def set_rules(self, r: Rules) -> None:
        def select(combo: QComboBox, code: str):
            combo.setCurrentIndex(max(0, combo.findData(code)))

        self.g_replace_all.setChecked(r.replace_all)
        self.e_replace_all.setText(r.replace_all_text)
        self.e_find.setText(r.find)
        self.e_replace.setText(r.replace_with)
        self.c_match_case.setChecked(r.match_case)
        self.c_regex.setChecked(r.use_regex)
        self.t_replacements.blockSignals(True)
        self.t_replacements.setRowCount(0)
        for find, replace in r.replacements:
            self._add_replacement_row(find, replace)
        self.t_replacements.blockSignals(False)
        self.s_remove_pos.setValue(r.remove_pos)
        self.s_remove_count.setValue(r.remove_count)
        self.c_remove_end.setChecked(r.remove_from_end)
        self.s_trim_left.setValue(r.trim_left)
        self.s_trim_right.setValue(r.trim_right)
        self.e_insert_text.setText(r.insert_text)
        self.s_insert_pos.setValue(r.insert_pos)
        self.c_insert_end.setChecked(r.insert_from_end)
        select(self.cb_case, r.case)
        self.e_prefix.setText(r.prefix)
        self.e_suffix.setText(r.suffix)
        select(self.cb_date, r.date_mode)
        self.e_date_format.setText(r.date_format)
        select(self.cb_date_position, r.date_position)
        self.e_date_sep.setText(r.date_separator)
        self._update_date_fields()
        self.g_numbering.setChecked(r.numbering)
        self.s_num_start.setValue(r.num_start)
        self.s_num_step.setValue(r.num_step)
        self.s_num_padding.setValue(r.num_padding)
        select(self.cb_num_position, r.num_position)
        self.e_num_sep.setText(r.num_separator)
        select(self.cb_ext, r.ext_mode)
        self.e_ext.setText(r.ext_text)
        self.e_ext.setEnabled(r.ext_mode == "replace")
        self._changed()

    def file_options(self) -> dict:
        return {
            "filter": self.e_filter.text(),
            "recursive": self.c_recursive.isChecked(),
            "hidden": self.c_hidden.isChecked(),
            "sort": self.cb_sort.currentData(),
            "reverse": self.c_reverse.isChecked(),
        }

    def file_options_from_settings(self, opts: dict | None = None) -> None:
        opts = opts if opts is not None else self.settings.get("files", {})
        self.e_filter.setText(opts.get("filter", ""))
        self.c_recursive.setChecked(bool(opts.get("recursive", False)))
        self.c_hidden.setChecked(bool(opts.get("hidden", False)))
        self.cb_sort.setCurrentIndex(max(0, self.cb_sort.findData(opts.get("sort", "name"))))
        self.c_reverse.setChecked(bool(opts.get("reverse", False)))

    # --- Lista dei file --------------------------------------------------------------------

    def add_paths(self, items: list[Path]) -> None:
        """Ricorda file e cartelle aggiunti: la lista si ricalcola da loro quando cambiano filtro e opzioni."""
        known = {engine.name_key(s) for s in self.sources}
        added = False
        for item in items:
            item = item.absolute()
            key = engine.name_key(item)
            if not (item.is_dir() or item.is_file()):
                continue
            # Riaggiungere un file o una cartella riporta in lista anche ciò che era stato tolto a mano
            restored = {k for k in self.excluded if k == key or k.startswith(key + os.sep)}
            if restored:
                self.excluded -= restored
                added = True
            if key not in known:
                known.add(key)
                self.sources.append(item)
                added = True
        if added:
            self.rebuild_list()

    def rebuild_list(self, *_):
        opts = self.file_options()
        known: set[str] = set()
        paths: list[Path] = []
        for source in self.sources:
            if source.is_dir():
                found = engine.collect_files(source, opts["recursive"], opts["filter"], opts["hidden"])
            elif source.is_file() and engine.matches_filter(source.name, opts["filter"]):
                found = [source]
            else:
                found = []
            for p in found:
                key = engine.name_key(p)
                if key not in known and key not in self.excluded:
                    known.add(key)
                    paths.append(p)
        if self.cb_sort.currentData() == "manual":
            # In ordine manuale i file già in lista restano dove l'utente li ha messi; i nuovi vanno in fondo
            previous = {engine.name_key(p): i for i, p in enumerate(self.paths)}
            paths.sort(key=lambda p: previous.get(engine.name_key(p), len(previous)))
        self.paths = paths
        debug_log(f"lista: {[p.name for p in paths]}")
        self.resort()

    def resort(self, *_):
        manual = self.cb_sort.currentData() == "manual"
        self.c_reverse.setEnabled(not manual)
        if not manual:
            self.paths = engine.sort_paths(self.paths, self.cb_sort.currentData(), self.c_reverse.isChecked())
        self.update_path_bar()
        self._changed()

    def move_selected(self, step: int) -> None:
        """Sposta su o giù i file selezionati; la numerazione segue l'ordine della lista."""
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()}, reverse=step > 0)
        if not rows or (step < 0 and rows[0] == 0) or (step > 0 and rows[0] == len(self.paths) - 1):
            return
        for row in rows:
            self.paths[row], self.paths[row + step] = self.paths[row + step], self.paths[row]
        self.cb_sort.blockSignals(True)
        self.cb_sort.setCurrentIndex(self.cb_sort.findData("manual"))
        self.cb_sort.blockSignals(False)
        self.c_reverse.setEnabled(False)
        self.refresh_preview()
        selection = self.table.selectionModel()
        selection.clearSelection()
        for row in rows:
            selection.select(self.model.index(row + step, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.table.scrollTo(self.model.index(rows[-1] + step, 0))

    def folders(self) -> list[Path]:
        """Cartelle da cui vengono i file in lista: quelle aggiunte e quelle dei singoli file."""
        found: dict[str, Path] = {}
        for source in self.sources:
            folder = source if source.is_dir() else source.parent
            found.setdefault(engine.name_key(folder), folder)
        return list(found.values())

    def update_path_bar(self) -> None:
        if not hasattr(self, "e_path") or (self.e_path.hasFocus() and self.e_path.isModified()):
            return
        folders = self.folders()
        self.e_path.setEnabled(len(folders) <= 1)
        self.e_path.setText(str(folders[0]) if len(folders) == 1 else "")
        self.e_path.setPlaceholderText(tr("path_multiple") if len(folders) > 1 else tr("path_placeholder"))
        self.e_path.setModified(False)
        self._set_path_error(False)

    def _set_path_error(self, error: bool) -> None:
        self.e_path.setStyleSheet("QLineEdit { border: 1px solid #cf222e; }" if error else "")
        self.e_path.setToolTip(tr("path_invalid") if error else "")

    def open_typed_path(self) -> None:
        """Passa alla cartella scritta nella barra: la lista diventa il contenuto di quella cartella."""
        text = self.e_path.text().strip().strip('"')
        folder = Path(text).expanduser() if text else None
        if folder is None or not folder.is_dir():
            self._set_path_error(True)
            return
        folder = folder.absolute()
        self.e_path.setModified(False)
        if [engine.name_key(f) for f in self.folders()] == [engine.name_key(folder)] and \
                all(s.is_dir() for s in self.sources):
            self.update_path_bar()
            return
        self.settings["last_dir"] = str(folder)
        self.sources, self.excluded = [folder], set()
        self.rebuild_list()

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("select_files"), self.settings.get("last_dir", ""))
        if files:
            self.settings["last_dir"] = str(Path(files[0]).parent)
            self.add_paths([Path(f) for f in files])

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("select_folder"), self.settings.get("last_dir", ""))
        if folder:
            self.settings["last_dir"] = folder
            self.add_paths([Path(folder)])

    def remove_selected(self):
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        if rows:
            self.excluded.update(engine.name_key(p) for i, p in enumerate(self.paths) if i in rows)
            self.paths = [p for i, p in enumerate(self.paths) if i not in rows]
            self.refresh_preview()

    def clear_list(self):
        self.paths, self.sources, self.excluded = [], [], set()
        self.update_path_bar()
        self.refresh_preview()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])

    # --- Anteprima ed esecuzione -----------------------------------------------------------

    def refresh_preview(self):
        self.plan = engine.build_plan(self.paths, self.get_rules())
        self.model.set_plan(self.plan)
        ok = sum(1 for i in self.plan if i.status == Status.OK)
        bad = sum(1 for i in self.plan if i.status not in (Status.OK, Status.UNCHANGED))
        if self.plan:
            self.lbl_summary.setText(tr("summary", total=len(self.plan), ok=ok, bad=bad))
        else:
            self.lbl_summary.setText(tr("drop_hint"))
        self.btn_rename.setEnabled(ok > 0)
        self.act_rename.setEnabled(ok > 0)
        self.act_export.setEnabled(ok > 0)
        self.act_undo.setEnabled(JOURNAL_FILE.exists())

    def _replace_paths(self, mapping: dict[Path, Path]) -> None:
        self.paths = [mapping.get(p, p) for p in self.paths]
        self.sources = [mapping.get(p, p) for p in self.sources]
        self.update_path_bar()

    def _report(self, result: engine.RenameResult, key: str) -> None:
        if result.errors:
            details = "\n".join(f"{p.name}: {msg}" for p, msg in result.errors[:20])
            QMessageBox.warning(self, tr("done_title"), tr("done_with_errors", count=len(result.done),
                                                            errors=len(result.errors), details=details))
        else:
            QMessageBox.information(self, tr("done_title"), tr(key, count=len(result.done)))

    def do_rename(self):
        self.preview_timer.stop()
        self.refresh_preview()
        ok = sum(1 for i in self.plan if i.status == Status.OK)
        bad = sum(1 for i in self.plan if i.status not in (Status.OK, Status.UNCHANGED))
        if not ok:
            QMessageBox.information(self, tr("app_title"), tr("nothing_to_rename"))
            return
        text = tr("confirm_with_problems", count=ok, bad=bad) if bad else tr("confirm_rename", count=ok)
        if QMessageBox.question(self, tr("confirm_title"), text) != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = engine.apply_plan(self.plan)
            if result.done:
                engine.save_journal(JOURNAL_FILE, result.done)
            self._replace_paths(dict(result.done))
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_preview()
        self._report(result, "done")

    def do_undo(self):
        done = engine.load_journal(JOURNAL_FILE)
        if not done:
            QMessageBox.information(self, tr("app_title"), tr("undo_nothing"))
            return
        if QMessageBox.question(self, tr("confirm_title"), tr("confirm_undo", count=len(done))) != QMessageBox.Yes:
            return
        result = engine.undo(done)
        engine.pop_journal(JOURNAL_FILE)
        self._replace_paths({new: old for old, new in result.done})
        self.refresh_preview()
        self._report(result, "undo_done")

    def export_script(self):
        pairs = [(i.source, i.target) for i in self.plan if i.status == Status.OK]
        if not pairs:
            return
        windows = sys.platform == "win32"
        ext = "bat" if windows else "sh"
        name_filter = tr("script_filter_bat") if windows else tr("script_filter_sh")
        start = os.path.join(self.settings.get("last_dir", ""), f"rinomina.{ext}")
        path, _ = QFileDialog.getSaveFileName(self, tr("export_title"), start, name_filter)
        if not path:
            return
        rename_path = Path(path)
        if rename_path.suffix.lower() != f".{ext}":
            rename_path = rename_path.with_name(rename_path.name + f".{ext}")
        undo_path = rename_path.with_name(f"{rename_path.stem}-annulla.{ext}")
        try:
            for target, script_pairs in ((rename_path, pairs), (undo_path, [(b, a) for a, b in pairs])):
                target.write_text(engine.generate_script(script_pairs, ext), encoding="utf-8", newline="")
                if not windows:
                    target.chmod(0o755)
        except OSError as exc:
            QMessageBox.critical(self, tr("error_title"), str(exc))
            return
        QMessageBox.information(self, tr("export_title"), tr("export_done", rename=rename_path, undo=undo_path))

    # --- Regole salvate, lingua e chiusura --------------------------------------------------

    def save_preset(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("save_preset"), "", tr("preset_filter"))
        if path:
            if not path.lower().endswith(".json"):
                path += ".json"
            data = {"massiverenamer": 1, "rules": self.get_rules().to_dict(), "files": self.file_options()}
            try:
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                self._remember_preset(path)
            except OSError as exc:
                QMessageBox.critical(self, tr("error_title"), str(exc))

    def load_preset(self, path: str | None = None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("load_preset"), "", tr("preset_filter"))
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.set_rules(Rules.from_dict(data["rules"]))
            if isinstance(data.get("files"), dict):
                self.file_options_from_settings(data["files"])
            self._remember_preset(path)
        except FileNotFoundError:
            self._forget_preset(path)
            QMessageBox.critical(self, tr("error_title"), tr("recent_missing", path=path))
        except (OSError, ValueError, KeyError, TypeError):
            QMessageBox.critical(self, tr("error_title"), tr("preset_error"))

    MAX_RECENT = 8

    def _remember_preset(self, path: str) -> None:
        path = str(Path(path).absolute())
        recent = [p for p in self.settings.get("recent_presets", []) if p != path]
        self.settings["recent_presets"] = [path] + recent[: self.MAX_RECENT - 1]

    def _forget_preset(self, path: str) -> None:
        self.settings["recent_presets"] = [p for p in self.settings.get("recent_presets", []) if p != str(path)]

    def _fill_recent_menu(self) -> None:
        self.m_recent.clear()
        recent = self.settings.get("recent_presets", [])
        for path in recent:
            action = self.m_recent.addAction(Path(path).stem)
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _=False, p=path: self.load_preset(p))
        if recent:
            self.m_recent.addSeparator()
            self.m_recent.addAction(tr("recent_clear"), lambda: self.settings.update(recent_presets=[]))
        else:
            self.m_recent.addAction(tr("recent_empty")).setEnabled(False)

    def change_language(self, code: str):
        if code == current_language():
            return
        rules, opts = self.get_rules(), self.file_options()
        set_language(code)
        self.settings["language"] = code
        self._build_ui()
        self.set_rules(rules)
        self.file_options_from_settings(opts)
        self.update_path_bar()
        self.refresh_preview()

    def toggle_context_menu(self, on: bool):
        try:
            integration.install(tr("context_label")) if on else integration.uninstall()
        except OSError as exc:
            QMessageBox.critical(self, tr("error_title"), str(exc))
        self.act_context.blockSignals(True)
        self.act_context.setChecked(integration.is_installed())
        self.act_context.blockSignals(False)
        if on and integration.is_installed():
            QMessageBox.information(self, tr("context_menu"), tr("context_done_win" if sys.platform == "win32" else "context_done_mac"))

    def show_about(self):
        text = tr("about_text", version=__version__).replace("\n", "<br>")
        link = f'<a href="{DONATE_URL}">{DONATE_URL.removeprefix("https://")}</a>'
        QMessageBox.about(self, tr("about"), f"<p>{text}</p><p>{tr('donate_text')}<br>{link}</p>")

    def open_donate(self):
        QDesktopServices.openUrl(QUrl(DONATE_URL))

    def closeEvent(self, event):
        self.settings["rules"] = self.get_rules().to_dict()
        self.settings["files"] = self.file_options()
        save_settings(self.settings)
        super().closeEvent(event)


class Application(QApplication):
    """Su macOS i file trascinati sull'icona o aperti con «Apri con» arrivano come evento, non come argomenti."""

    window: MainWindow | None = None
    pending: list[Path] = []

    def event(self, event):
        if event.type() == QEvent.FileOpen:
            self.open_paths([Path(event.file())])
            return True
        return super().event(event)

    def open_paths(self, paths: list[Path]) -> None:
        debug_log(f"ricevuti: {[str(p) for p in paths]}")
        if self.window is None:
            self.pending.extend(paths)
            return
        self.window.add_paths(paths)
        self.window.setWindowState(self.window.windowState() & ~Qt.WindowMinimized)
        self.window.raise_()
        self.window.activateWindow()


def self_test(app: QApplication, settings: dict) -> int:
    """Controllo usato dalla CI sull'eseguibile impacchettato: se mancasse una libreria tolta per
    alleggerirlo, qui il programma si fermerebbe con un errore invece di aprire la finestra."""
    from . import updater

    updater._ssl_context()  # certificati e OpenSSL per l'aggiornamento automatico
    SingleInstance(f"MassiveRenamer-selftest-{os.getpid()}")
    window = MainWindow(settings, [])
    window.show()
    QTimer.singleShot(1500, app.quit)
    app.exec()
    window.close()
    print(f"self-test ok: {__version__}, {app.style().name()}, {app.platformName()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = Application(argv)
    app.setApplicationName("MassiveRenamer")
    app.setOrganizationName("MassiveRenamer")
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("resources") / "icon.png")))
    settings = load_settings()
    set_language(settings.get("language") or default_language())
    paths = [a for a in argv[1:] if not a.startswith("-")]

    if "--self-test" in argv:
        return self_test(app, settings)

    # Un secondo avvio (per esempio dal tasto destro su più file) passa i file alla finestra aperta
    instance = SingleInstance()
    if not instance.acquire():
        if instance.send(paths):
            return 0
    instance.received.connect(lambda received: app.open_paths([Path(p) for p in received]))

    debug_log(f"avvio: {paths}")
    window = MainWindow(settings, paths)
    app.window = window
    window.add_paths(app.pending)
    window.show()
    integration.refresh(tr("context_label"))
    QTimer.singleShot(1500, window.updates.start)
    return app.exec()
