"""Motore di rinomina: regole, anteprima, esecuzione sicura, annullamento e script.

Non dipende dall'interfaccia grafica, così può essere testato e riusato da riga di comando.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, fields
from enum import Enum
from pathlib import Path

CASE_MODES = ("keep", "upper", "lower", "title", "sentence")
EXT_MODES = ("keep", "replace", "upper", "lower", "remove")
NUM_POSITIONS = ("before", "after", "replace")
SORT_KEYS = ("name", "ext", "mtime", "size")

WINDOWS_INVALID_CHARS = set('<>:"/\\|?*')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}
MAX_NAME_BYTES = 255


class RuleError(ValueError):
    """Regola non valida (per esempio un'espressione regolare sbagliata)."""


@dataclass
class Rules:
    """Insieme delle regole, applicate in quest'ordine:
    nome sostituito per intero, cerca/sostituisci, taglio, maiuscole/minuscole,
    testo prima/dopo, numerazione, estensione."""

    replace_all: bool = False
    replace_all_text: str = ""
    find: str = ""
    replace_with: str = ""
    match_case: bool = False
    use_regex: bool = False
    trim_left: int = 0
    trim_right: int = 0
    case: str = "keep"
    prefix: str = ""
    suffix: str = ""
    numbering: bool = False
    num_start: int = 1
    num_step: int = 1
    num_padding: int = 1
    num_position: str = "after"
    num_separator: str = "_"
    ext_mode: str = "keep"
    ext_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Rules":
        """Crea le regole da un dizionario, ignorando chiavi sconosciute o di tipo errato."""
        rules = cls()
        for f in fields(cls):
            if f.name in data and isinstance(data[f.name], type(getattr(rules, f.name))):
                setattr(rules, f.name, data[f.name])
        return rules


def split_name(name: str) -> tuple[str, str]:
    """Divide in (nome, estensione senza punto). I file nascosti come '.bashrc' non hanno estensione."""
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return name, ""
    return stem, ext


def _title_case(text: str) -> str:
    text = text.lower()
    return re.sub(r"(^|[\s_\-.(\[])(\w)", lambda m: m.group(1) + m.group(2).upper(), text)


def _apply_case(text: str, mode: str) -> str:
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return _title_case(text)
    if mode == "sentence":
        return text[:1].upper() + text[1:].lower()
    return text


class Renamer:
    """Applica le regole a un nome. Compila una volta sola l'eventuale espressione regolare."""

    def __init__(self, rules: Rules):
        self.rules = rules
        self._pattern = None
        if rules.find:
            flags = 0 if rules.match_case else re.IGNORECASE
            source = rules.find if rules.use_regex else re.escape(rules.find)
            try:
                self._pattern = re.compile(source, flags)
            except re.error as exc:
                raise RuleError(str(exc)) from exc

    def new_name(self, name: str, index: int) -> str:
        """Nuovo nome per il file in posizione `index` (da 0) nella lista."""
        r = self.rules
        stem, ext = split_name(name)

        if r.replace_all:
            stem = r.replace_all_text
        if self._pattern is not None:
            replacement = r.replace_with if r.use_regex else (lambda _m: r.replace_with)
            try:
                stem = self._pattern.sub(replacement, stem)
            except (re.error, IndexError) as exc:
                raise RuleError(str(exc)) from exc
        if r.trim_left > 0:
            stem = stem[r.trim_left :]
        if r.trim_right > 0:
            stem = stem[: -r.trim_right] if r.trim_right < len(stem) else ""
        stem = _apply_case(stem, r.case)
        stem = f"{r.prefix}{stem}{r.suffix}"

        if r.numbering:
            number = str(r.num_start + index * r.num_step).zfill(max(1, r.num_padding))
            if r.num_position == "before":
                stem = f"{number}{r.num_separator}{stem}"
            elif r.num_position == "replace":
                stem = number
            else:
                stem = f"{stem}{r.num_separator}{number}"

        if r.ext_mode == "replace":
            ext = r.ext_text.lstrip(".")
        elif r.ext_mode == "upper":
            ext = ext.upper()
        elif r.ext_mode == "lower":
            ext = ext.lower()
        elif r.ext_mode == "remove":
            ext = ""

        return f"{stem}.{ext}" if ext else stem


class Status(str, Enum):
    OK = "ok"
    UNCHANGED = "unchanged"
    EMPTY = "empty"
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    EXISTS = "exists"
    ERROR = "error"


@dataclass
class PlanItem:
    source: Path
    new_name: str
    status: Status
    message: str = ""

    @property
    def target(self) -> Path:
        return self.source.with_name(self.new_name)


def name_key(path: Path | str, platform: str = sys.platform) -> str:
    """Chiave per confrontare i nomi: Windows e macOS di norma non distinguono maiuscole e minuscole,
    e macOS salva i nomi in Unicode decomposto."""
    text = unicodedata.normalize("NFC", str(path))
    return text if platform.startswith("linux") else text.casefold()


def validate_name(name: str, platform: str = sys.platform) -> str | None:
    """Restituisce il motivo per cui il nome non è valido, oppure None."""
    if not name:
        return "empty"
    if name in (".", "..") or "/" in name or "\0" in name:
        return "invalid_chars"
    if len(name.encode("utf-8")) > MAX_NAME_BYTES:
        return "too_long"
    if platform == "win32":
        if any(c in WINDOWS_INVALID_CHARS or ord(c) < 32 for c in name):
            return "invalid_chars"
        if name[-1] in " .":
            return "trailing_dot"
        if split_name(name)[0].upper() in WINDOWS_RESERVED or name.upper() in WINDOWS_RESERVED:
            return "reserved"
    elif platform == "darwin" and ":" in name:
        return "invalid_chars"
    return None


def build_plan(paths: list[Path], rules: Rules, platform: str = sys.platform) -> list[PlanItem]:
    """Calcola l'anteprima: nuovo nome e stato di ogni file, senza toccare il disco
    (tranne per controllare se il nome di destinazione esiste già)."""
    try:
        renamer = Renamer(rules)
        names = [renamer.new_name(p.name, i) for i, p in enumerate(paths)]
    except RuleError as exc:
        return [PlanItem(p, p.name, Status.ERROR, str(exc)) for p in paths]

    plan: list[PlanItem] = []
    for path, new in zip(paths, names):
        if new == path.name:
            plan.append(PlanItem(path, new, Status.UNCHANGED))
            continue
        problem = validate_name(new, platform)
        # Nome rimasto vuoto con la sola estensione: diventerebbe un file nascosto come ".txt".
        if problem == "empty" or (new.startswith(".") and not path.name.startswith(".")):
            plan.append(PlanItem(path, new, Status.EMPTY))
        elif problem:
            plan.append(PlanItem(path, new, Status.INVALID, problem))
        else:
            plan.append(PlanItem(path, new, Status.OK))

    # Ogni file occupa il nome finale, o quello attuale se non verrà rinominato.
    final = [i.target if i.status == Status.OK else i.source for i in plan]
    counts: dict[str, int] = {}
    for p in final:
        k = name_key(p, platform)
        counts[k] = counts.get(k, 0) + 1
    source_keys = {name_key(p, platform) for p in paths}

    for item, p in zip(plan, final):
        if item.status != Status.OK:
            continue
        key = name_key(p, platform)
        if counts[key] > 1:
            item.status = Status.DUPLICATE
        elif key not in source_keys and os.path.lexists(p):
            item.status = Status.EXISTS
    return plan


@dataclass
class RenameResult:
    done: list[tuple[Path, Path]]
    errors: list[tuple[Path, str]]


def rename_pairs(pairs: list[tuple[Path, Path]]) -> RenameResult:
    """Rinomina in due passaggi attraverso nomi temporanei, così funzionano anche gli scambi
    (a→b, b→a) e i cambi solo di maiuscole/minuscole sui dischi che non le distinguono.
    Non sovrascrive mai un file esistente."""
    staged: list[tuple[Path, Path, Path]] = []
    errors: list[tuple[Path, str]] = []

    for src, dst in pairs:
        tmp = src.with_name(f".mr-tmp-{uuid.uuid4().hex[:12]}")
        try:
            os.rename(src, tmp)
            staged.append((src, tmp, dst))
        except OSError as exc:
            errors.append((src, exc.strerror or str(exc)))

    done: list[tuple[Path, Path]] = []
    for src, tmp, dst in staged:
        try:
            if os.path.lexists(dst):
                raise FileExistsError(17, "il file di destinazione esiste già")
            os.rename(tmp, dst)
            done.append((src, dst))
        except OSError as exc:
            errors.append((src, exc.strerror or str(exc)))
            try:
                os.rename(tmp, src)
            except OSError as exc2:
                errors.append((tmp, f"impossibile ripristinare {src.name}: {exc2}"))
    return RenameResult(done, errors)


def apply_plan(plan: list[PlanItem]) -> RenameResult:
    return rename_pairs([(i.source, i.target) for i in plan if i.status == Status.OK])


# --- Annullamento ---------------------------------------------------------------------------


def save_journal(path: Path, done: list[tuple[Path, Path]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"time": time.time(), "renames": [[str(a), str(b)] for a, b in done]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_journal(path: Path) -> list[tuple[Path, Path]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [(Path(a), Path(b)) for a, b in data["renames"]]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def undo(done: list[tuple[Path, Path]]) -> RenameResult:
    """Riporta i file ai nomi originali."""
    return rename_pairs([(b, a) for a, b in done])


# --- Script ---------------------------------------------------------------------------------


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def generate_script(pairs: list[tuple[Path, Path]], kind: str) -> str:
    """Script che esegue le rinomine: 'bat' per Windows, 'sh' per macOS/Linux.
    Usa anch'esso i nomi temporanei, per gli stessi motivi di rename_pairs."""
    temps = [f"mr-tmp-{i:05d}-{uuid.uuid4().hex[:6]}" for i in range(len(pairs))]
    if kind == "bat":

        def q(text: str) -> str:
            return '"' + str(text).replace("%", "%%") + '"'

        lines = ["@echo off", "chcp 65001 >nul", "rem Creato da MassiveRenamer"]
        lines += [f"ren {q(src)} {q(t)}" for (src, _), t in zip(pairs, temps)]
        lines += [f"ren {q(src.with_name(t))} {q(dst.name)}" for (src, dst), t in zip(pairs, temps)]
        return "\r\n".join(lines) + "\r\n"
    if kind == "sh":
        lines = ["#!/bin/sh", "# Creato da MassiveRenamer"]
        lines += [f"mv -n -- {_sh_quote(str(src))} {_sh_quote(str(src.with_name(t)))}" for (src, _), t in zip(pairs, temps)]
        lines += [f"mv -n -- {_sh_quote(str(src.with_name(t)))} {_sh_quote(str(dst))}" for (src, dst), t in zip(pairs, temps)]
        return "\n".join(lines) + "\n"
    raise ValueError(kind)


# --- Raccolta e ordinamento dei file --------------------------------------------------------


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


def matches_filter(name: str, pattern: str) -> bool:
    """Filtro tipo '*.jpg;*.png' (vuoto = tutti i file), senza distinzione di maiuscole."""
    masks = [m.strip() for m in pattern.split(";") if m.strip()]
    return not masks or any(fnmatch.fnmatch(name.casefold(), m.casefold()) for m in masks)


def collect_files(folder: Path, recursive: bool = False, pattern: str = "", include_hidden: bool = False) -> list[Path]:
    result: list[Path] = []
    for root, dirs, files in os.walk(folder):
        if not include_hidden:
            dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if (include_hidden or not f.startswith(".")) and matches_filter(f, pattern):
                result.append(Path(root) / f)
        if not recursive:
            break
    return sort_paths(result)


def sort_paths(paths: list[Path], key: str = "name", reverse: bool = False) -> list[Path]:
    def stat_or_zero(p: Path, attr: str) -> float:
        try:
            return getattr(p.stat(), attr)
        except OSError:
            return 0

    if key == "mtime":
        func = lambda p: (stat_or_zero(p, "st_mtime"), _natural_key(p.name))
    elif key == "size":
        func = lambda p: (stat_or_zero(p, "st_size"), _natural_key(p.name))
    elif key == "ext":
        func = lambda p: (split_name(p.name)[1].casefold(), _natural_key(p.name))
    else:
        func = lambda p: (_natural_key(p.name), _natural_key(str(p.parent)))
    return sorted(paths, key=func, reverse=reverse)


def config_dir() -> Path:
    """Cartella delle impostazioni dell'utente, diversa per sistema operativo."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "MassiveRenamer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MassiveRenamer"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "massiverenamer"
