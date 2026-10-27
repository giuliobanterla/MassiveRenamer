# MassiveRenamer

Rinomina molti file in una volta, su **Windows** e **macOS**. Si ispira a
[Lupas Rename](https://sourceforge.net/app/lupas-rename/), che esiste solo per Windows e non viene più aggiornato dal 2004.

Interfaccia in italiano e in inglese, scelta dal menu **Lingua**.

## Funzioni

- **Sostituisci tutto il nome** con un testo nuovo.
- **Cerca e sostituisci**, con o senza distinzione tra maiuscole e minuscole, anche con espressioni regolari.
- **Taglia** un numero di caratteri da sinistra e/o da destra.
- **Maiuscole e minuscole**: tutto maiuscolo, tutto minuscolo, Iniziali Maiuscole, solo la prima maiuscola.
- **Aggiungi testo** prima e dopo il nome.
- **Numerazione** con valore iniziale, incremento, numero di cifre, posizione (prima, dopo o al posto del nome) e separatore.
- **Estensione**: sostituita, maiuscola, minuscola o rimossa.
- **Anteprima immediata**, con i problemi segnalati prima di rinominare: nomi duplicati, file già esistenti, caratteri non ammessi dal sistema, nomi riservati di Windows, nomi vuoti.
- **Annulla l'ultima rinomina**, anche dopo aver chiuso il programma.
- **Esporta script** (`.bat` su Windows, `.sh` su macOS) per rifare la rinomina, insieme allo script che la annulla.
- **Salva e carica le regole** in un file `.json`. Le ultime regole usate vengono ricordate.
- Aggiunta di file e cartelle, anche trascinandoli nella finestra, con filtro (`*.jpg;*.png`), sottocartelle e file nascosti a scelta.
- Ordinamento per nome (i numeri sono ordinati come numeri: `img2` prima di `img10`), estensione, data di modifica o dimensione. La numerazione segue quest'ordine.

Gli spostamenti avvengono in due passaggi attraverso nomi temporanei. Così funzionano anche gli scambi di nome tra due file
e i cambi solo di maiuscole/minuscole (`foto.jpg` → `FOTO.JPG`), che su Windows e macOS sono un caso difficile.
Un file esistente non viene mai sovrascritto.

## Avvio da sorgente

Serve Python 3.10 o più recente.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m massiverenamer
```

Su Windows il percorso è `.venv\Scripts\python`.

I percorsi di file o cartelle passati come argomenti vengono aggiunti subito alla lista.

## Test

```bash
.venv/bin/python -m pytest
```

## Eseguibili

`python build.py` crea l'eseguibile per il sistema su cui gira, nella cartella `dist/`:

- su macOS `MassiveRenamer.app`
- su Windows `MassiveRenamer.exe`, un file unico che non va installato

Non si può creare l'eseguibile Windows da un Mac. Per questo il workflow GitHub Actions `.github/workflows/build.yml`
esegue i test e crea gli eseguibili per Windows x64, macOS Apple Silicon (arm64) e macOS Intel (x64) a ogni pull request
e a ogni merge su `main`. Si scaricano dalla pagina del workflow, alla voce *Artifacts*.

Gli eseguibili non sono firmati. Al primo avvio:

- **macOS**: clic destro sull'app → *Apri* → *Apri*.
- **Windows**: in SmartScreen, *Ulteriori informazioni* → *Esegui comunque*.

## Dove salva i dati

| Sistema | Cartella |
|---|---|
| Windows | `%APPDATA%\MassiveRenamer` |
| macOS | `~/Library/Application Support/MassiveRenamer` |

`settings.json` contiene lingua, ultime regole e opzioni. `last_rename.json` contiene l'ultima rinomina, per poterla annullare.

## Struttura

- `massiverenamer/engine.py`: regole, anteprima, rinomina, annullamento e script. Non dipende dall'interfaccia.
- `massiverenamer/gui.py`: interfaccia Qt (PySide6).
- `massiverenamer/i18n.py`: testi in italiano e inglese.
- `tests/`: test del motore.

## Contribuire

`main` è protetto: ogni modifica passa da un branch e da una pull request, e il merge è possibile solo
quando i controlli `windows-x64`, `macos-arm64` e `macos-x64` sono verdi. Dependabot propone ogni lunedì
gli aggiornamenti delle dipendenze Python e delle GitHub Actions.

## Sostieni il progetto

MassiveRenamer è gratuito. Se ti è utile e vuoi contribuire, puoi fare una donazione con
[PayPal](https://www.paypal.me/GiulioBanterla). Il link è anche nel menu **Aiuto** del programma.

## Licenza

GNU Lesser General Public License 2.1: vedi [LICENSE](LICENSE). È compatibile con PySide6, che usa la stessa famiglia di licenze (LGPL).
