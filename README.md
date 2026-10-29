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

**Firma.** Nelle release l'app per macOS è firmata con un Developer ID e notarizzata da Apple, quindi si apre
senza avvisi. Le build delle pull request hanno solo la firma ad-hoc: al primo avvio clic destro sull'app → *Apri*.
L'eseguibile per Windows non è firmato: in SmartScreen, *Ulteriori informazioni* → *Esegui comunque*.

La firma su macOS la fa `build.py` se trova queste variabili d'ambiente (in CI arrivano dai segreti del repository,
solo nel workflow di release):

| Variabile | Segreto | Contenuto |
|---|---|---|
| `MACOS_SIGN_IDENTITY` | `MACOS_CERTIFICATE`, `MACOS_CERTIFICATE_PASSWORD` | certificato Developer ID (.p12 in base64) e la sua password |
| `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` | stessi nomi | account Apple, team e password specifica per app per la notarizzazione |

Senza segreti la release viene pubblicata lo stesso, con la sola firma ad-hoc.

**Icona.** `tools/make_icons.py` la disegna e la salva in `assets/icon/` (PNG, `.ico`, `.icns`) e in `massiverenamer/resources/`.

## Aggiornamenti automatici

Al primo avvio MassiveRenamer chiede se può controllare una volta al giorno se c'è una nuova versione.
Prima della risposta non contatta nessuno; la scelta si cambia dal menu **Aiuto** (su macOS dal menu
dell'app), dove c'è anche **Cerca aggiornamenti…** per controllare subito.

- Viene contattata solo l'API di GitHub per leggere l'ultima release di questo repository; non si inviano dati personali.
- Il file per il proprio sistema si scarica solo dalle release di questo repository e deve avere lo stesso hash
  indicato in `SHA256SUMS.txt` della release.
- Su macOS, se l'app in uso è firmata con un Developer ID, la nuova deve essere firmata dallo stesso team e
  notarizzata, altrimenti l'aggiornamento viene rifiutato.
- **Installa e riavvia**: su Windows il nuovo `.exe` prende il posto di quello attuale e parte subito; su macOS,
  dopo la chiusura, la nuova `.app` sostituisce la vecchia (che torna al suo posto se qualcosa va storto) e si apre.
- Se il programma gira da sorgente o la sua cartella non è scrivibile, c'è **Scarica…**, che apre la pagina della release.
- Per provare un aggiornamento: `MASSIVERENAMER_PRETEND_VERSION=0.0.1` fa credere al programma di essere più vecchio.

## Pubblicare una nuova versione

1. Pull request che aggiorna `__version__` in `massiverenamer/__init__.py`, merge in `main`.
2. Tag annotato sul commit di `main`: `git tag -a v0.2.0 -m "MassiveRenamer 0.2.0"` e `git push origin v0.2.0`.
3. Il workflow `.github/workflows/release.yml` controlla che il tag corrisponda alla versione, esegue test e build
   sulle tre piattaforme e pubblica la release con `MassiveRenamer-windows-x64.exe`, `MassiveRenamer-macos-arm64.zip`,
   `MassiveRenamer-macos-x64.zip` e `SHA256SUMS.txt`. Da quel momento i programmi installati la propongono.

## Dove salva i dati

| Sistema | Cartella |
|---|---|
| Windows | `%APPDATA%\MassiveRenamer` |
| macOS | `~/Library/Application Support/MassiveRenamer` |

`settings.json` contiene lingua, ultime regole, opzioni e scelta sugli aggiornamenti. `last_rename.json` contiene l'ultima rinomina, per poterla annullare.

## Struttura

- `massiverenamer/engine.py`: regole, anteprima, rinomina, annullamento e script. Non dipende dall'interfaccia.
- `massiverenamer/gui.py`: interfaccia Qt (PySide6).
- `massiverenamer/updater.py` e `update_ui.py`: aggiornamento automatico.
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

GNU General Public License 3.0: vedi [LICENSE](LICENSE). Le dipendenze sono compatibili: PySide6/Qt (LGPL-3.0) e certifi (MPL-2.0).
Le versioni fino alla 0.1.1 sono state pubblicate con la licenza LGPL-2.1.
