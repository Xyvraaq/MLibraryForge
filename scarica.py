from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


# Tutti i percorsi sono relativi a questo file, non alla cartella da cui
# viene lanciato Python (cosi avvia.bat puo essere eseguito ovunque).
BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "playlist.txt"
OUTPUT_DIR = BASE_DIR / "Musica"
TEMP_DIR = OUTPUT_DIR / ".tmp"
NOT_DOWNLOADED_FILE = BASE_DIR / "brani_non_scaricati.txt"

RESULTS = 8
MIN_SCORE = 0.58
MIN_MARGIN = 0.06

VERSION_PHRASES = (
    "original mix",
    "extended mix",
    "extended version",
    "club mix",
    "radio edit",
    "radio mix",
    "vocal mix",
    "vocal",
    "dub mix",
    "dub",
    "remix",
    "rework",
    "bootleg",
    "edit",
    "instrumental",
    "acoustic",
    "live",
    "remaster",
)

# Parole tipiche dei risultati non musicali che causavano falsi positivi.
JUNK_TERMS = (
    "netflix",
    "recap",
    "recapitulation",
    "episode",
    "episodio",
    "season",
    "stagione",
    "trailer",
    "reaction",
    "reacting",
    "review",
    "commentary",
    "explained",
    "ending explained",
    "interview",
    "podcast",
    "news",
    "documentary",
    "documentario",
    "gameplay",
    "walkthrough",
    "highlights",
    "movie",
    "film",
    "karaoke",
    "cover",
    "tribute",
    "shorts",
)


def normalize(text: str) -> str:
    """Normalizza il testo per confrontarlo, senza modificarlo nel filename."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[\[\](){}_:;,.!?/\\|+_=\-]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {token for token in normalize(text).split() if len(token) > 1}


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def token_overlap(expected: str, actual: str) -> float:
    expected_tokens = tokens(expected)
    actual_tokens = tokens(actual)
    if not expected_tokens or not actual_tokens:
        return 0.0
    return len(expected_tokens & actual_tokens) / len(expected_tokens)


def clean_filename(name: str) -> str:
    # Windows non consente questi caratteri. Il testo Spotify resta invariato
    # quando il filesystem lo permette, con la sola rimozione degli invalidi.
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    return name.rstrip(" .")


def parse_track(query: str) -> tuple[str, str]:
    if " - " in query:
        artist, title = query.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", query.strip()


def version_phrases(text: str) -> set[str]:
    normalized = normalize(text)
    return {phrase for phrase in VERSION_PHRASES if phrase in normalized}


def has_junk(text: str) -> bool:
    normalized = normalize(text)
    return any(term in normalized for term in JUNK_TERMS)


def search_youtube(query: str) -> list[dict]:
    command = [
        "yt-dlp",
        "--extractor-args",
        "youtube:player_client=android",
        f"ytsearch{RESULTS}:{query}",
        "--flat-playlist",
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print("Errore nella ricerca:")
            print(result.stderr.strip())
            return []

        data = json.loads(result.stdout)
        return [entry for entry in data.get("entries", []) if entry]
    except (OSError, json.JSONDecodeError) as error:
        print(f"Errore nella ricerca: {error}")
        return []


def candidate_is_music(query: str, result: dict) -> bool:
    artist, track = parse_track(query)
    title = result.get("title", "") or ""
    uploader = result.get("uploader", "") or result.get("channel", "") or ""
    duration = result.get("duration")

    if has_junk(f"{title} {uploader}"):
        return False
    if duration is not None and (duration < 35 or duration > 3600):
        return False

    # Un brano plausibile deve contenere almeno una parola distintiva del
    # titolo; questo elimina quasi tutti i recap con artista simile.
    track_tokens = tokens(track)
    title_tokens = tokens(title)
    if track_tokens and not (track_tokens & title_tokens):
        return False

    if artist:
        artist_tokens = {word for word in tokens(artist) if len(word) >= 3}
        searchable = title_tokens | tokens(uploader)
        if artist_tokens and not (artist_tokens & searchable):
            if similarity(artist, uploader) < 0.42 and similarity(artist, title) < 0.42:
                return False
    return True


def score_result(query: str, result: dict) -> float:
    artist, track = parse_track(query)
    title = result.get("title", "") or ""
    uploader = result.get("uploader", "") or result.get("channel", "") or ""

    title_score = max(similarity(track, title), token_overlap(track, title))
    artist_score = max(similarity(artist, uploader), token_overlap(artist, uploader))
    full_score = similarity(query, title)

    # Se il canale non riporta l'artista, un titolo "Artista - Brano" puo
    # comunque dimostrarlo.
    artist_score = max(artist_score, token_overlap(artist, title))
    score = title_score * 0.48 + artist_score * 0.32 + full_score * 0.20

    requested_versions = version_phrases(query)
    candidate_versions = version_phrases(title)
    if requested_versions:
        score += 0.10 * len(requested_versions & candidate_versions)
        score -= 0.12 * len(requested_versions - candidate_versions)
    else:
        # Non trasformare una richiesta della versione normale in un remix o
        # in una cover solo perche la parola "mix" aumenta la somiglianza.
        unwanted = {"remix", "bootleg", "rework", "acoustic", "live", "karaoke"}
        score -= 0.08 * len(unwanted & candidate_versions)

    return score


def choose_result(query: str, results: list[dict]) -> list[tuple[float, dict]]:
    scored = []
    for result in results:
        if candidate_is_music(query, result):
            scored.append((score_result(query, result), result))
    return sorted(scored, key=lambda item: item[0], reverse=True)


def result_url(result: dict) -> str | None:
    return result.get("webpage_url") or (
        f"https://www.youtube.com/watch?v={result.get('id')}"
        if result.get("id")
        else None
    )


def select_result(
    results: list[tuple[float, dict]],
    allow_automatic: bool = True,
) -> tuple[float, dict, bool] | None:
    """Restituisce il risultato scelto e se la scelta e stata manuale."""
    while True:
        automatic_label = "INVIO=automatico" if allow_automatic else "INVIO=salta"
        choice = input(
            f"\nScegli un risultato [1-{len(results)}], {automatic_label}, s=salta: "
        ).strip().lower()
        if choice == "":
            if not allow_automatic:
                return None
            score, result = results[0]
            return score, result, False
        if choice in {"s", "skip"}:
            return None
        if choice.isdigit():
            position = int(choice)
            if 1 <= position <= len(results):
                score, result = results[position - 1]
                return score, result, True
        print(f"Scelta non valida. Inserisci un numero da 1 a {len(results)}, INVIO o s.")


def expected_filename(index: int, query: str) -> str:
    # Il prefisso mantiene l'ordine Spotify; il testo dopo il prefisso e il
    # testo della playlist, salvo i caratteri vietati da Windows.
    return clean_filename(f"{index:03d} - {query}.mp3")


def same_spotify_track(path: Path, query: str) -> bool:
    clean_query = clean_filename(query)
    stem = path.stem
    return stem == clean_query or stem.endswith(f" - {clean_query}")


def find_existing_track(query: str, expected: Path) -> Path | None:
    if expected.exists() and same_spotify_track(expected, query):
        return expected
    for path in OUTPUT_DIR.glob("*.mp3"):
        if same_spotify_track(path, query):
            return path
    return None


def migrate_legacy_files(tracks: list[str]) -> None:
    """Sposta solo vecchi audio che corrispondono alla playlist corrente."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in BASE_DIR.glob("*.mp3"):
        if not any(same_spotify_track(path, track) for track in tracks):
            continue
        destination = OUTPUT_DIR / path.name
        if destination.exists():
            continue
        try:
            shutil.move(str(path), str(destination))
            print(f"Spostato in Musica: {path.name}")
        except OSError as error:
            print(f"Avviso: non posso spostare {path.name}: {error}")


def save_not_downloaded(tracks: list[str]) -> None:
    """Scrive una traccia per riga, senza duplicati."""
    unique_tracks = list(dict.fromkeys(tracks))
    content = "\n".join(unique_tracks)
    if content:
        content += "\n"
    NOT_DOWNLOADED_FILE.write_text(content, encoding="utf-8")


def write_exact_metadata(filename: Path, artist: str, track: str) -> bool:
    """Scrive i tag ID3 Spotify senza toccare la copertina incorporata."""
    if not track and not artist:
        return True

    # Mutagen modifica solo i due frame interessati e conserva APIC/copertina.
    try:
        from mutagen.id3 import ID3, TIT2, TPE1
        from mutagen.mp3 import MP3

        audio = MP3(str(filename), ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        if track:
            audio.tags.delall("TIT2")
            audio.tags.add(TIT2(encoding=3, text=[track]))
        if artist:
            audio.tags.delall("TPE1")
            audio.tags.add(TPE1(encoding=3, text=[artist]))
        audio.save(v2_version=3)
        return True
    except ImportError:
        pass
    except Exception as error:
        print(f"Avviso: mutagen non ha aggiornato i tag: {error}")

    # Fallback per installazioni che hanno ffmpeg ma non il modulo mutagen.
    temporary = filename.with_name(f".{filename.stem}.metadata.mp3")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(filename),
        "-map",
        "0",
        "-c",
        "copy",
        "-id3v2_version",
        "3",
    ]
    if track:
        command.extend(["-metadata", f"title={track}"])
    if artist:
        command.extend(["-metadata", f"artist={artist}"])
    command.append(str(temporary))

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0 and temporary.exists():
            temporary.replace(filename)
            return True
        temporary.unlink(missing_ok=True)
    except OSError:
        pass
    return False


def download(url: str, filename: Path, artist: str, track: str) -> bool:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        "yt-dlp",
        "--extractor-args",
        "youtube:player_client=android",
        url,
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--no-playlist",
        "--no-part",
        "-o",
        str(TEMP_DIR / "%(id)s.%(ext)s"),
        "--print",
        "after_move:filepath",
    ]

    # Imposta i tag dopo l'estrazione, cosi il titolo del video non sostituisce
    # il testo Spotify. La sostituzione e passata come argomento separato:
    # anche caratteri come ':' nel titolo restano quindi sicuri su Windows.
    if track:
        command.extend([
            "--replace-in-metadata",
            "title",
            ".*",
            track.replace("\\", "\\\\"),
            "--parse-metadata",
            "%(title)s:%(meta_title)s",
        ])
    if artist:
        command.extend([
            "--replace-in-metadata",
            "uploader",
            ".*",
            artist.replace("\\", "\\\\"),
            "--parse-metadata",
            "%(uploader)s:%(meta_artist)s",
        ])
    command.extend(["--embed-metadata", "--embed-thumbnail"])

    print("\nDownload in corso...\n")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print("ERRORE durante il download:")
        print(result.stderr.strip())
        return False

    candidates = []
    for line in result.stdout.splitlines():
        candidate = Path(line.strip().strip('"'))
        if candidate.suffix.lower() == ".mp3" and candidate.exists():
            candidates.append(candidate)
    if not candidates:
        candidates = list(TEMP_DIR.glob("*.mp3"))
    if not candidates:
        print("ERRORE: yt-dlp ha terminato senza creare un MP3.")
        return False

    source = max(candidates, key=lambda path: path.stat().st_mtime)
    if filename.exists():
        print(f"ERRORE: la destinazione esiste gia: {filename.name}")
        return False
    shutil.move(str(source), str(filename))
    if not write_exact_metadata(filename, artist, track):
        print("Avviso: metadati Spotify non aggiornati; servono mutagen oppure ffmpeg.")
    return True


def print_banner() -> None:
    print(
        r"""
============================================================
                    MLibraryForge
============================================================
""".strip()
    )


def main() -> None:
    print_banner()
    print()
    if not INPUT_FILE.exists():
        print(f"ERRORE: non trovo {INPUT_FILE}")
        input("Premi INVIO per uscire...")
        return

    tracks = [
        line.strip()
        for line in INPUT_FILE.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    migrate_legacy_files(tracks)
    not_downloaded: list[str] = []
    save_not_downloaded(not_downloaded)

    total = len(tracks)
    print(f"Trovate {total} tracce.")
    print(f"Cartella di destinazione: {OUTPUT_DIR}")

    for index, query in enumerate(tracks, start=1):
        print("\n" + "=" * 70)
        print(f"[{index}/{total}] {query}")
        print("=" * 70)

        filename = Path(expected_filename(index, query))
        final_path = OUTPUT_DIR / filename
        existing = find_existing_track(query, final_path)
        if existing:
            artist, track = parse_track(query)
            # Se l'indice e cambiato, aggiorna solo il prefisso: l'identita
            # del brano resta il testo Spotify, quindi non si riscarica nulla.
            if existing != final_path and not final_path.exists():
                existing.rename(final_path)
                existing = final_path
                print(f"Gia scaricato; aggiornata la posizione: {final_path.name}")
            else:
                print(f"Gia scaricato: {existing.name}")
            if not write_exact_metadata(existing, artist, track):
                print("Avviso: metadati Spotify non aggiornati; servono mutagen oppure ffmpeg.")
            continue

        print(f"Cerco {RESULTS} risultati musicali su YouTube...")
        results = choose_result(query, search_youtube(query))
        if not results:
            print("NESSUN RISULTATO MUSICALE AFFIDABILE: saltato.")
            not_downloaded.append(query)
            save_not_downloaded(not_downloaded)
            continue

        print("\nRISULTATI VALIDI:")
        for position, (score, result) in enumerate(results, start=1):
            title = result.get("title", "Titolo sconosciuto")
            uploader = result.get("uploader", result.get("channel", ""))
            print(f"{position}. {title} | {uploader} | score {score:.2f}")

        automatic_score, automatic_result = results[0]
        second_score = results[1][0] if len(results) > 1 else 0.0
        ambiguous = (
            automatic_score < MIN_SCORE
            or automatic_score - second_score < MIN_MARGIN
        )

        if ambiguous:
            print("\nATTENZIONE: corrispondenza bassa o ambigua.")
            selected = select_result(results, allow_automatic=True)
            if selected is None:
                print("Saltato.")
                not_downloaded.append(query)
                save_not_downloaded(not_downloaded)
                continue
        else:
            selected = (automatic_score, automatic_result, False)

        best_score, best, manual_selection = selected
        title = best.get("title", "Titolo sconosciuto")
        uploader = best.get("uploader", best.get("channel", ""))
        url = result_url(best)

        print("\nSCELTO:")
        print(f"Selezione: {'manuale' if manual_selection else 'automatica'}")
        print(f"Titolo : {title}")
        print(f"Canale : {uploader}")
        print(f"Score  : {best_score:.2f}")
        print(f"URL    : {url}")

        if not url:
            print("ERRORE: il risultato non contiene un URL scaricabile; saltato.")
            not_downloaded.append(query)
            save_not_downloaded(not_downloaded)
            continue

        artist, track = parse_track(query)
        if download(url, final_path, artist, track):
            print(f"OK -> {final_path.name}")
        else:
            print("Download fallito.")
            not_downloaded.append(query)
            save_not_downloaded(not_downloaded)

    print("\n" + "=" * 70)
    print("OPERAZIONE COMPLETATA")
    print("=" * 70)
    input("\nPremi INVIO per chiudere...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperazione interrotta.")
        sys.exit(130)
