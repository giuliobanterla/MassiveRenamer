"""Disegna l'icona di MassiveRenamer e la salva in tutti i formati che servono.

Uso: .venv/bin/python tools/make_icons.py
Risultato: assets/icon/ (PNG, icon.ico, icon.icns su macOS) e massiverenamer/resources/icon.png.
"""

import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon"
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def document(p: QPainter, rect: QRectF, color: QColor) -> None:
    """Foglio con l'angolo piegato."""
    fold = rect.width() * 0.22
    path = QPainterPath()
    path.moveTo(rect.left(), rect.top() + 28)
    path.quadTo(rect.left(), rect.top(), rect.left() + 28, rect.top())
    path.lineTo(rect.right() - fold, rect.top())
    path.lineTo(rect.right(), rect.top() + fold)
    path.lineTo(rect.right(), rect.bottom() - 28)
    path.quadTo(rect.right(), rect.bottom(), rect.right() - 28, rect.bottom())
    path.lineTo(rect.left() + 28, rect.bottom())
    path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - 28)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 45))
    p.drawPath(path.translated(0, 10))
    p.setBrush(color)
    p.drawPath(path)
    corner = QPainterPath()
    corner.moveTo(rect.right() - fold, rect.top())
    corner.lineTo(rect.right() - fold, rect.top() + fold - 12)
    corner.quadTo(rect.right() - fold, rect.top() + fold, rect.right() - fold + 12, rect.top() + fold)
    corner.lineTo(rect.right(), rect.top() + fold)
    corner.closeSubpath()
    p.setBrush(color.darker(118))
    p.drawPath(corner)


def draw(p: QPainter) -> None:
    """Disegno su una tela 1024 × 1024, con la griglia di macOS: piastrella 824 × 824 e margine 100."""
    p.setRenderHint(QPainter.Antialiasing)
    tile = QRectF(100, 100, 824, 824)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(tile.translated(0, 12), 185, 185)
    gradient = QLinearGradient(QPointF(512, 100), QPointF(512, 924))
    gradient.setColorAt(0, QColor("#22C55E"))
    gradient.setColorAt(1, QColor("#0F766E"))
    p.setBrush(QBrush(gradient))
    p.drawRoundedRect(tile, 185, 185)

    # Tre fogli a ventaglio: tanti file
    for dx, dy, shade in ((-110, -40, "#CFE9DF"), (-55, -20, "#E6F4EE")):
        document(p, QRectF(300 + dx, 230 + dy, 420, 540), QColor(shade))
    front = QRectF(330, 250, 420, 540)
    document(p, front, QColor("#FFFFFF"))

    # Righe di testo e il campo del nome evidenziato con il cursore
    p.setBrush(QColor("#B6D7CB"))
    for y, w in ((560, 300), (620, 260), (680, 220)):
        p.drawRoundedRect(QRectF(390, y, w, 26), 13, 13)
    field = QRectF(370, 380, 340, 110)
    p.setBrush(QColor("#FACC15"))
    p.drawRoundedRect(field, 26, 26)
    font = QFont("Helvetica", 1)
    font.setPixelSize(78)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#14532D"))
    p.drawText(field.adjusted(28, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, "Aa1")
    p.setPen(QPen(QColor("#14532D"), 12))
    p.drawLine(QPointF(590, 405), QPointF(590, 465))


def render(size: int) -> QImage:
    master = QImage(1024, 1024, QImage.Format_ARGB32_Premultiplied)
    master.fill(Qt.transparent)
    painter = QPainter(master)
    draw(painter)
    painter.end()
    return master if size == 1024 else master.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def png_bytes(image: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[QImage]) -> None:
    """File .ico con più dimensioni, ognuna salvata come PNG (formato accettato da Windows Vista in poi)."""
    blobs = [png_bytes(i) for i in images]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for image, blob in zip(images, blobs):
        side = image.width() % 256  # 256 si scrive 0
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + entries + b"".join(blobs))


def main() -> None:
    QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])
    OUT.mkdir(parents=True, exist_ok=True)
    images = {size: render(size) for size in SIZES}
    for size, image in images.items():
        image.save(str(OUT / f"icon-{size}.png"))
    write_ico(OUT / "icon.ico", [images[s] for s in (16, 32, 48, 64, 128, 256)])
    resources = ROOT / "massiverenamer" / "resources"
    resources.mkdir(exist_ok=True)
    images[256].save(str(resources / "icon.png"))

    if sys.platform == "darwin":
        iconset = OUT / "MassiveRenamer.iconset"
        shutil.rmtree(iconset, ignore_errors=True)
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            images[size].save(str(iconset / f"icon_{size}x{size}.png"))
            images[size * 2 if size * 2 in images else 1024].save(str(iconset / f"icon_{size}x{size}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
        shutil.rmtree(iconset)


if __name__ == "__main__":
    main()
