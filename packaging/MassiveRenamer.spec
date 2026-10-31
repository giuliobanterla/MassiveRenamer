# Specifica PyInstaller usata da build.py: .app su macOS, .exe in un solo file su Windows.
#
# Rispetto a quello che PyInstaller raccoglierebbe da solo, toglie le parti di Qt che il programma
# non usa (QML/Quick, PDF, SVG, OpenGL, tastiera virtuale, plugin di immagini e input, backend TLS
# di Qt, traduzioni di Qt): l'eseguibile pesa circa la metà. `MassiveRenamer --self-test`, lanciato
# dalla CI, controlla che l'eseguibile alleggerito parta davvero.
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - SPECPATH viene da PyInstaller

# Moduli Qt non usati: framework su macOS (QtPdf.framework), DLL su Windows (Qt6Pdf.dll), moduli Python
UNUSED_QT = re.compile(r"^(lib)?Qt6?(Pdf|Qml|Quick|Svg|OpenGL|VirtualKeyboard|Labs)", re.IGNORECASE)
UNUSED_PLUGIN_DIRS = {"imageformats", "iconengines", "platforminputcontexts", "generic", "tls", "networkinformation"}
UNUSED_PLATFORMS = re.compile(r"q(minimal|offscreen|direct2d|vnc)", re.IGNORECASE)
# Solo per OpenGL software e Direct3D, non servono a un'interfaccia a widget
UNUSED_FILES = {"opengl32sw.dll", "d3dcompiler_47.dll"}


def wanted(dest: str) -> bool:
    parts = dest.replace("\\", "/").split("/")
    if parts[-1].lower() in UNUSED_FILES:
        return False
    if any(UNUSED_QT.match(part) for part in parts):
        return False
    for i, part in enumerate(parts[:-1]):
        if part == "plugins" and parts[i + 1] in UNUSED_PLUGIN_DIRS:
            return False
        if part == "plugins" and parts[i + 1] == "platforms" and UNUSED_PLATFORMS.search(parts[-1]):
            return False
        if part == "translations" and "PySide6" in parts:
            return False
    return True


a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "massiverenamer", "resources"), "massiverenamer/resources")],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtSvg",
              "PySide6.QtOpenGL", "PySide6.QtDBus"],
)
a.binaries = [entry for entry in a.binaries if wanted(entry[0])]
a.datas = [entry for entry in a.datas if wanted(entry[0])]
pyz = PYZ(a.pure)  # noqa: F821

if sys.platform == "darwin":
    exe = EXE(  # noqa: F821
        pyz, a.scripts, [], exclude_binaries=True, name="MassiveRenamer", console=False,
        icon=os.path.join(ROOT, "assets", "icon", "icon.icns"),
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="MassiveRenamer")  # noqa: F821
    app = BUNDLE(  # noqa: F821
        coll, name="MassiveRenamer.app", icon=os.path.join(ROOT, "assets", "icon", "icon.icns"),
        bundle_identifier="info.gbss.massiverenamer",
    )
else:
    exe = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [], name="MassiveRenamer", console=False,
        icon=os.path.join(ROOT, "assets", "icon", "icon.ico"),
        version=os.environ.get("MASSIVERENAMER_VERSION_FILE"),
    )
