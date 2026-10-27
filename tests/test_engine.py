import os
import subprocess
import sys
from pathlib import Path

import pytest

from massiverenamer import engine
from massiverenamer.engine import Renamer, Rules, Status, build_plan, split_name, validate_name


def rename(name, index=0, **kwargs):
    return Renamer(Rules(**kwargs)).new_name(name, index)


def make(tmp_path, *names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.write_text(n)
        paths.append(p)
    return paths


def test_split_name():
    assert split_name("foto.jpg") == ("foto", "jpg")
    assert split_name("archivio.tar.gz") == ("archivio.tar", "gz")
    assert split_name(".bashrc") == (".bashrc", "")
    assert split_name("README") == ("README", "")


def test_rules_individually():
    assert rename("foto.jpg", replace_all=True, replace_all_text="vacanze") == "vacanze.jpg"
    assert rename("IMG_001.jpg", find="img_", replace_with="Foto ") == "Foto 001.jpg"
    assert rename("IMG_001.jpg", find="img_", replace_with="x", match_case=True) == "IMG_001.jpg"
    assert rename("a1b22.txt", find=r"\d+", replace_with="#", use_regex=True) == "a#b#.txt"
    assert rename("a.txt", find="a", replace_with=r"\1") == r"\1.txt"
    assert rename("abcdef.txt", trim_left=2, trim_right=1) == "cde.txt"
    assert rename("abc.txt", trim_right=10) == ".txt"
    assert rename("ciao mondo.txt", case="upper") == "CIAO MONDO.txt"
    assert rename("CIAO MONDO.txt", case="title") == "Ciao Mondo.txt"
    assert rename("CIAO MONDO.txt", case="sentence") == "Ciao mondo.txt"
    assert rename("x.txt", prefix="2026-", suffix="_v2") == "2026-x_v2.txt"
    assert rename("x.JPG", ext_mode="lower") == "x.jpg"
    assert rename("x.jpg", ext_mode="replace", ext_text=".png") == "x.png"
    assert rename("x.jpg", ext_mode="remove") == "x"


def test_numbering():
    r = dict(numbering=True, num_start=1, num_step=2, num_padding=3)
    assert rename("a.jpg", 0, **r) == "a_001.jpg"
    assert rename("a.jpg", 2, **r) == "a_005.jpg"
    assert rename("a.jpg", 0, **r, num_position="before", num_separator=" - ") == "001 - a.jpg"
    assert rename("a.jpg", 1, **r, num_position="replace") == "003.jpg"


def test_bad_regex_marks_all_items(tmp_path):
    paths = make(tmp_path, "a.txt", "b.txt")
    plan = build_plan(paths, Rules(find="(", use_regex=True))
    assert all(i.status == Status.ERROR for i in plan)


def test_validate_name():
    assert validate_name("ok.txt", "win32") is None
    assert validate_name("a:b.txt", "win32") == "invalid_chars"
    assert validate_name("a:b.txt", "darwin") == "invalid_chars"
    assert validate_name("a:b.txt", "linux") is None
    assert validate_name("CON.txt", "win32") == "reserved"
    assert validate_name("nome.", "win32") == "trailing_dot"
    assert validate_name("x" * 256, "darwin") == "too_long"
    assert validate_name("", "darwin") == "empty"


def test_plan_statuses(tmp_path):
    paths = make(tmp_path, "a.txt", "b.txt", "keep.txt")
    (tmp_path / "existing.txt").write_text("")
    plan = build_plan(paths[:2], Rules(replace_all=True, replace_all_text="same"))
    assert [i.status for i in plan] == [Status.DUPLICATE, Status.DUPLICATE]

    plan = build_plan([paths[0]], Rules(replace_all=True, replace_all_text="existing"))
    assert plan[0].status == Status.EXISTS

    # Un file che resta com'è occupa ancora il suo nome.
    plan = build_plan([paths[0], paths[2]], Rules(find="a", replace_with="keep"))
    assert plan[0].status == Status.DUPLICATE and plan[1].status == Status.UNCHANGED

    plan = build_plan([paths[0]], Rules(trim_right=5))
    assert plan[0].status == Status.EMPTY


def test_apply_and_undo_with_swap(tmp_path):
    a, b = make(tmp_path, "a.txt", "b.txt")
    # Scambio: a→b e b→a, impossibile con una rinomina diretta.
    plan = build_plan([a, b], Rules(find="a", replace_with="X"))
    plan[0].new_name, plan[0].status = "b.txt", Status.OK
    plan[1].new_name, plan[1].status = "a.txt", Status.OK
    result = engine.apply_plan(plan)
    assert not result.errors
    assert (tmp_path / "a.txt").read_text() == "b.txt"
    assert (tmp_path / "b.txt").read_text() == "a.txt"

    result = engine.undo(result.done)
    assert not result.errors
    assert (tmp_path / "a.txt").read_text() == "a.txt"


def test_case_only_rename(tmp_path):
    (p,) = make(tmp_path, "foto.jpg")
    plan = build_plan([p], Rules(case="upper", ext_mode="upper"))
    assert plan[0].status == Status.OK
    result = engine.apply_plan(plan)
    assert not result.errors
    assert os.listdir(tmp_path) == ["FOTO.JPG"]


def test_never_overwrites(tmp_path):
    a, other = make(tmp_path, "a.txt", "other.txt")
    result = engine.rename_pairs([(a, other)])
    assert result.errors and not result.done
    assert a.read_text() == "a.txt" and other.read_text() == "other.txt"
    assert sorted(os.listdir(tmp_path)) == ["a.txt", "other.txt"]


def test_journal_roundtrip(tmp_path):
    j = tmp_path / "sub" / "j.json"
    pairs = [(tmp_path / "à.txt", tmp_path / "b.txt")]
    engine.save_journal(j, pairs)
    assert engine.load_journal(j) == pairs
    assert engine.load_journal(tmp_path / "missing.json") == []


@pytest.mark.skipif(sys.platform == "win32", reason="script sh")
def test_sh_script_runs(tmp_path):
    a, b = make(tmp_path, "it's a.txt", "b.txt")
    pairs = [(a, tmp_path / "b.txt"), (b, tmp_path / "it's a.txt")]
    script = tmp_path / "r.sh"
    script.write_text(engine.generate_script(pairs, "sh"))
    subprocess.run(["sh", str(script)], check=True)
    assert (tmp_path / "b.txt").read_text() == "it's a.txt"
    assert (tmp_path / "it's a.txt").read_text() == "b.txt"


@pytest.mark.skipif(sys.platform != "win32", reason="script bat")
def test_bat_script_runs(tmp_path):
    a, b = make(tmp_path, "100% a.txt", "b.txt")
    pairs = [(a, tmp_path / "b.txt"), (b, tmp_path / "100% a.txt")]
    script = tmp_path / "r.bat"
    script.write_text(engine.generate_script(pairs, "bat"), encoding="utf-8", newline="")
    subprocess.run(["cmd", "/c", str(script)], check=True)
    assert (tmp_path / "b.txt").read_text() == "100% a.txt"


def test_bat_script_escapes_percent():
    text = engine.generate_script([(Path("C:/x/100%.txt"), Path("C:/x/b.txt"))], "bat")
    assert "100%%.txt" in text and "\r\n" in text


def test_collect_and_sort(tmp_path):
    make(tmp_path, "img10.jpg", "img2.jpg", "note.txt", ".hidden.jpg")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "img1.JPG").write_text("")
    names = [p.name for p in engine.collect_files(tmp_path, pattern="*.jpg")]
    assert names == ["img2.jpg", "img10.jpg"]
    names = [p.name for p in engine.collect_files(tmp_path, recursive=True, pattern="*.jpg")]
    assert names == ["img1.JPG", "img2.jpg", "img10.jpg"]
    assert len(engine.collect_files(tmp_path, include_hidden=True)) == 4


def test_rules_from_dict_ignores_bad_data():
    r = Rules.from_dict({"prefix": "x", "trim_left": "nope", "unknown": 1})
    assert r.prefix == "x" and r.trim_left == 0
