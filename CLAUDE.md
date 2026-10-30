# MassiveRenamer

Rinomina molti file in una volta, su Windows e macOS; ispirato a Lupas Rename.
Python 3.10+, interfaccia PySide6 (Qt), GPL-3.0 (fino alla 0.1.1 LGPL-2.1). Repository pubblico: tutto quello che viene
committato è pubblico, quindi niente dati personali, nomi di host o segreti.

## Struttura

```
massiverenamer/engine.py   regole, anteprima, rinomina in due passaggi, annullamento, script; nessuna dipendenza da Qt
massiverenamer/gui.py      interfaccia PySide6
massiverenamer/updater.py  aggiornamento automatico dalle release GitHub (senza Qt); update_ui.py la barra
massiverenamer/i18n.py     testi italiano/inglese
massiverenamer/integration.py  menu del tasto destro (registro HKCU su Windows, Azione rapida su macOS)
massiverenamer/single_instance.py  un secondo avvio passa i file alla finestra aperta (QLockFile + QLocalServer)
massiverenamer/exif.py     data di scatto da JPEG/TIFF senza dipendenze
tests/                     pytest: motore, aggiornamento, integrazione (l'interfaccia si prova a mano)
build.py                   eseguibile con PyInstaller (.app su macOS, .exe su Windows); firma e notarizza su macOS
tools/make_icons.py        disegna l'icona (assets/icon/, massiverenamer/resources/)
packaging/macos/           entitlements per l'hardened runtime
```

## Build e test

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m massiverenamer
.venv/bin/python build.py
```

- Ogni nuovo testo dell'interfaccia va in `i18n.py` in **entrambe** le lingue.
- La logica sta in `engine.py`, testabile senza interfaccia; `gui.py` resta un sottile strato sopra.
- Per vedere cosa riceve l'app impacchettata (Azione rapida, `open -a`, secondo avvio):
  `MASSIVERENAMER_DEBUG_LOG=/tmp/mr.log dist/MassiveRenamer.app/Contents/MacOS/MassiveRenamer`.

## Piattaforme

La CI (`.github/workflows/build.yml`) esegue test e build su `windows-x64`, `macos-arm64` e
`macos-x64`; questi tre controlli sono obbligatori per il merge. Il Mac del maintainer è Intel x64:
in locale gira solo macOS x64, Windows e arm64 sono verificati solo dalla CI. Il codice che dipende
dal sistema va dietro `sys.platform` e va pensato per entrambi i rami (nomi non validi, maiuscole e
minuscole, script `.bat`/`.sh`).

## Flusso di lavoro

- `main` è protetto: si lavora su un branch, si apre una PR con `gh`, si aspetta la CI verde
  (`gh run watch <id> --exit-status`). Merge (squash) solo quando il maintainer lo chiede.
- Mai push diretto su `main`. Mai creare o pubblicare tag o release senza un sì esplicito.
  `.claude/settings.json` chiede conferma per questi comandi. Un tag `v*` lancia `release.yml`, che
  pubblica la release: i programmi installati la propongono subito come aggiornamento.
- Firma macOS: Developer ID team `D3694MQ8D9` (lo stesso di GBFileCopier); segreti del repository solo nel
  workflow di release. In locale: `MACOS_SIGN_IDENTITY="Developer ID Application: Giulio Banterla (D3694MQ8D9)" .venv/bin/python build.py`
  (firma senza notarizzare). Windows non è firmato.
- Release: PR che aggiorna `__version__` → merge → tag annotato `vX.Y.Z` su quel commit (il workflow
  rifiuta un tag diverso da `__version__`) → controllare gli asset e `SHA256SUMS.txt`.
- Commit, PR, commenti e testi del progetto in italiano.
