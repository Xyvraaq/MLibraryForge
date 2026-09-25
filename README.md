# MLibraryForge

[![MLibraryForge](https://i.ibb.co/PJPhrvc/mlf.png)](#readme)

MLibraryForge e uno strumento Python basato su [yt-dlp](https://github.com/yt-dlp/yt-dlp) che trasforma una playlist testuale in una libreria di file MP3 ordinati, con copertina e metadati coerenti con i dati forniti dall'utente.

Il progetto e pensato per playlist esportate manualmente da Spotify nel formato:

```text
Artista - Titolo
Artista - Titolo (Extended Mix)
Artista - Titolo (Remix)
```

## Caratteristiche

- Cerca 8 risultati YouTube per ogni brano.
- Confronta artista, titolo e nome del canale.
- Valuta le versioni come Remix, Extended, Vocal, Dub, Original Mix e simili.
- Scarta risultati poco attendibili come recap, episodi, trailer, podcast, reaction, cover, ecc.
- Chiede conferma quando la corrispondenza è bassa o ambigua.
- Mantiene l'ordine originale della playlist con un prefisso numerico a tre cifre.
- Conserva il testo Spotify nel nome del file, rimuovendo solo i caratteri vietati da Windows.
- Scrive nei metadati il titolo e l'artista della playlist, non il titolo o il canale YouTube.
- Incorpora copertina e metadati nel file MP3.
- Salta i brani gia scaricati anche se il numero iniziale è cambiato.
- Aggiorna i metadati dei file gia presenti senza riscaricarli.
- Sposta in `Musica` i vecchi MP3 nella cartella principale quando corrispondono alla playlist corrente.
-  Crea `brani_non_scaricati.txt` con i nomi delle tracce rimaste non scaricate.

## Requisiti

- Windows 10 o superiore.
- Python 3.10 o superiore.
- `yt-dlp` disponibile nel `PATH`.
- `ffmpeg` disponibile nel `PATH`.
- `mutagen` consigliato per aggiornare velocemente i tag ID3.

Controlla l'installazione con:

```powershell
python --version
yt-dlp --version
ffmpeg -version
```

Installa o aggiorna i componenti Python con:

```powershell
python -m pip install -U yt-dlp mutagen
```

```powershell
winget install Gyan.FFmpeg
```

## Installazione

Metti nella stessa cartella:

```text
MLibraryForge/
├─ scarica.py
├─ playlist.txt
└─ avvia.bat        (facoltativo)
```

Il file `playlist.txt` deve contenere una traccia per riga:

```text
Daft Punk - Giorgio by Moroder
Deadmau5 - Strobe (Extended Mix)
```

Non servono credenziali Spotify: MLibraryForge utilizza il testo gia presente in `playlist.txt` come fonte per ordine, nomi e metadati.

Puoi utilizzare TuneMyMusic per esportare in file .txt le tue playlist

## Utilizzo

Avvia `avvia.bat`, oppure esegui:

```powershell
python scarica.py
```

Alla prima esecuzione vengono create automaticamente:

```text
MLibraryForge/
├─ Musica/          # file MP3 finali
└─ Musica/.tmp/     # file temporanei durante il download
```

Nella cartella principale viene inoltre creato `brani_non_scaricati.txt`.
Contiene una traccia per riga e viene aggiornato durante l'esecuzione. A ogni
nuovo avvio viene ricreato da zero, quindi non conserva brani che nel frattempo
sono stati scaricati correttamente.

I file finali avranno nomi simili a:

```text
001 - Daft Punk - Giorgio by Moroder.mp3
002 - Deadmau5 - Strobe (Extended Mix).mp3
```

Il prefisso numerico serve solo a mantenere l'ordine della playlist. Il testo Spotify resta invariato dopo il prefisso, ad eccezione dei caratteri non consentiti da Windows.

## Ripresa e duplicati

MLibraryForge identifica un brano usando il testo Spotify, non soltanto il numero iniziale del filename.

Di conseguenza, se una traccia fallisce o la playlist viene modificata, al riavvio:

- i brani gia presenti non vengono riscaricati;
- il prefisso numerico puo essere aggiornato per riflettere il nuovo ordine;
- i file esistenti possono ricevere i metadati corretti;
- vengono cercate e scaricate solo le tracce mancanti.

## Metadati

Per ogni file vengono impostati:

```text
title  = Titolo dalla playlist.txt
artist = Artista dalla playlist.txt
```

La copertina viene incorporata dal risultato YouTube scelto. I metadati vengono prima richiesti a yt-dlp e poi verificati/scritti nuovamente da MLibraryForge con `mutagen` o, come fallback, con `ffmpeg`.

## Selezione dei risultati

La scelta considera:

- somiglianza del titolo;
- corrispondenza dell'artista nel titolo o nel canale;
- corrispondenza della versione richiesta;
- durata plausibile per un brano musicale;
- presenza di termini che indicano contenuti non musicali.

Quando i risultati migliori sono troppo simili tra loro o hanno un punteggio insufficiente, il programma chiede conferma invece di scaricare automaticamente un risultato incerto.

## Note d'uso

Usa MLibraryForge solo per contenuti che hai il diritto di scaricare e conserva i file nel rispetto delle leggi applicabili e dei termini dei servizi utilizzati.
