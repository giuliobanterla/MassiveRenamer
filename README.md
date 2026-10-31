# MassiveRenamer

Rinomina molti file in una volta, su **Windows** e **macOS**. Si ispira a
[Lupas Rename](https://sourceforge.net/app/lupas-rename/), che esiste solo per Windows e non viene più aggiornato dal 2004.

Interfaccia in italiano e in inglese, scelta dal menu **Lingua**.

## Funzioni

- **Sostituisci tutto il nome** con un testo nuovo.
- **Cerca e sostituisci**, con o senza distinzione tra maiuscole e minuscole, anche con espressioni regolari,
  con quante coppie cerca/sostituisci servono, applicate in ordine.
- **Togli caratteri in una posizione**: quanti e da quale posizione, contando dall'inizio o dalla fine.
- **Taglia** un numero di caratteri da sinistra e/o da destra.
- **Inserisci testo in una posizione**, contando i caratteri dall'inizio o dalla fine.
- **Maiuscole e minuscole**: tutto maiuscolo, tutto minuscolo, Iniziali Maiuscole, solo la prima maiuscola.
- **Aggiungi testo** prima e dopo il nome.
- **Data** prima, dopo o al posto del nome: data di modifica, di creazione o di scatto delle foto (EXIF di JPEG, TIFF e
  dei RAW basati su TIFF; se manca si usa la data di modifica), con formato a scelta (`%Y-%m-%d`, `%Y%m%d_%H%M`…).
- **Numerazione** con valore iniziale, incremento, numero di cifre, posizione (prima, dopo o al posto del nome) e separatore.
- **Estensione**: sostituita, maiuscola, minuscola o rimossa.
- **Barra del percorso** sopra la lista: mostra la cartella dei file e si può scrivere a mano (con completamento) per
  passare a un'altra cartella. Si disattiva quando i file vengono da più cartelle.
- **Anteprima immediata**, con le parti del nome che cambiano evidenziate in giallo e i problemi segnalati prima di rinominare: nomi duplicati, file già esistenti, caratteri non ammessi dal sistema, nomi riservati di Windows, nomi vuoti.
- **Annulla** le ultime rinomine (fino a 20, una alla volta), anche dopo aver chiuso il programma.
- **Esporta script** (`.bat` su Windows, `.sh` su macOS) per rifare la rinomina, insieme allo script che la annulla.
- **Salva e carica le regole** in un file `.json`, con il menu **File → Regole recenti** per ritrovarle. Le ultime regole usate vengono ricordate.
- Aggiunta di file e cartelle, anche trascinandoli nella finestra, con filtro (`*.jpg;*.png`), sottocartelle e file nascosti a scelta.
  Cambiando filtro o opzioni la lista si ricalcola subito; i file tolti a mano restano fuori finché non si riaggiunge la cartella.
- **Svuota lista** con il pulsante accanto a «Rinomina» o con ⌘⇧⌫ (macOS) / Ctrl+Shift+Backspace (Windows).
- **Menu del tasto destro** (menu File → «Aggiungi al menu del tasto destro»): «Rinomina con MassiveRenamer» su file e cartelle.
  Su Windows in Esplora risorse (su Windows 11 sotto «Mostra altre opzioni»), su macOS nelle Azioni rapide del Finder.
  Più file selezionati, o più avvii, finiscono nella stessa finestra.
- Ordinamento per nome (i numeri sono ordinati come numeri: `img2` prima di `img10`), estensione, data di modifica o dimensione. La numerazione segue quest'ordine.
- **Ordine manuale**: con ↑ e ↓ (o Alt+↑/↓) si spostano i file selezionati; l'ordine resta anche cambiando filtro.

Gli spostamenti avvengono in due passaggi attraverso nomi temporanei. Così funzionano anche gli scambi di nome tra due file
e i cambi solo di maiuscole/minuscole (`foto.jpg` → `FOTO.JPG`), che su Windows e macOS sono un caso difficile.
Un file esistente non viene mai sovrascritto.

## Download e installazione

Dalla pagina [Releases](https://github.com/giuliobanterla/MassiveRenamer/releases/latest):

| Sistema | File | Come si installa |
|---|---|---|
| Windows | `MassiveRenamer-setup-windows-x64.exe` | installer: per il solo utente, senza permessi da amministratore, con la voce nel menu Start, la voce facoltativa nel menu del tasto destro e la disinstallazione da *Impostazioni* → *App* |
| Windows | `MassiveRenamer-windows-x64.exe` | versione portatile: un file unico da avviare dove si vuole, senza installazione |
| macOS Apple Silicon | `MassiveRenamer-macos-arm64.dmg` | si apre il `.dmg` e si trascina MassiveRenamer in *Applicazioni* |
| macOS Intel | `MassiveRenamer-macos-x64.dmg` | come sopra |

Gli `.zip` per macOS contengono la stessa app e servono all'aggiornamento automatico.

## Avvio da sorgente

Serve Python 3.10 o più recente.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m massiverenamer
```

Su Windows il percorso è `.venv\Scripts\python`.

I percorsi di file o cartelle passati come argomenti vengono aggiunti subito alla lista; se il programma è già aperto,
finiscono nella finestra esistente. Con `MASSIVERENAMER_DEBUG_LOG=/percorso/file.log` il programma annota i file ricevuti.

## Test

```bash
.venv/bin/python -m pytest
```

I test comprendono anche l'interfaccia, eseguita senza schermo: le immagini della finestra finiscono in
`tests/screenshots/` e in CI si scaricano dagli artifact `screenshots-<piattaforma>`.

## Eseguibili

`python build.py` crea il programma per il sistema su cui gira, nella cartella `dist/`, con le opzioni di
`packaging/MassiveRenamer.spec` (che toglie le parti di Qt non usate: l'app per macOS pesa circa 70 MB invece di 104):

- su macOS `MassiveRenamer.app` e `MassiveRenamer.dmg`, l'immagine disco con l'app e il collegamento ad *Applicazioni*;
- su Windows la cartella `MassiveRenamer/`, l'installer `MassiveRenamer-setup.exe` creato da quella cartella con
  [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`packaging/windows/MassiveRenamer.iss`; senza Inno Setup
  l'installer viene saltato) e la versione portatile `MassiveRenamer-portable.exe`, in un file unico.
  Il programma installato si avvia più in fretta di quello portatile, che a ogni avvio si scompatta in una cartella temporanea.

In CI ogni pull request prova anche l'installer (installazione silenziosa, avvio, voce del tasto destro,
disinstallazione) e il `.dmg` (montaggio e avvio dell'app che contiene).

Non si può creare l'eseguibile Windows da un Mac. Per questo il workflow GitHub Actions `.github/workflows/build.yml`
esegue i test e crea gli eseguibili per Windows x64, macOS Apple Silicon (arm64) e macOS Intel (x64) a ogni pull request
e a ogni merge su `main`. Si scaricano dalla pagina del workflow, alla voce *Artifacts*.

**Firma.** Nelle release l'app e il `.dmg` per macOS sono firmati con un Developer ID e notarizzati da Apple,
quindi si aprono senza avvisi. Le build delle pull request hanno solo la firma ad-hoc: al primo avvio clic destro sull'app → *Apri*.
Installer ed eseguibile per Windows non sono firmati: in SmartScreen, *Ulteriori informazioni* → *Esegui comunque*.

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
- **Installa e riavvia**:
  - Windows, programma installato: dopo la chiusura parte il nuovo installer senza finestre, che poi riapre il programma;
  - Windows, versione portatile: il nuovo `.exe` prende il posto di quello attuale e parte subito;
  - macOS: dopo la chiusura la nuova `.app` sostituisce la vecchia (che torna al suo posto se qualcosa va storto) e si apre.
- Se il programma gira da sorgente o la sua cartella non è scrivibile, c'è **Scarica…**, che apre la pagina della release.
- Per provare un aggiornamento: `MASSIVERENAMER_PRETEND_VERSION=0.0.1` fa credere al programma di essere più vecchio.

## Pubblicare una nuova versione

1. Pull request che aggiorna `__version__` in `massiverenamer/__init__.py`, merge in `main`.
2. Tag annotato sul commit di `main`: `git tag -a v0.2.0 -m "MassiveRenamer 0.2.0"` e `git push origin v0.2.0`.
3. Il workflow `.github/workflows/release.yml` controlla che il tag corrisponda alla versione, esegue test e build
   sulle tre piattaforme e pubblica la release con `MassiveRenamer-setup-windows-x64.exe`, `MassiveRenamer-windows-x64.exe`,
   `MassiveRenamer-macos-arm64.dmg` e `.zip`, `MassiveRenamer-macos-x64.dmg` e `.zip` e `SHA256SUMS.txt`.
   Da quel momento i programmi installati la propongono.

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
- `massiverenamer/integration.py`: menu del tasto destro; `single_instance.py`: una sola finestra.
- `massiverenamer/exif.py`: data di scatto delle foto, senza dipendenze.
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
