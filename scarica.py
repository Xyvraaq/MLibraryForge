import subprocess
import json
import os
import re
import sys
from difflib import SequenceMatcher

INPUT_FILE = "playlist.txt"
OUTPUT_DIR = "Musica"
RESULTS = 5

os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalize(text):
    text = text.lower()

    # Rimuove accenti
    replacements = {
        "á": "a", "à": "a", "ä": "a",
        "é": "e", "è": "e", "ë": "e",
        "í": "i", "ì": "i", "ï": "i",
        "ó": "o", "ò": "o", "ö": "o",
        "ú": "u", "ù": "u", "ü": "u",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Normalizza separatori
    text = text.replace("&", " and ")
    text = re.sub(r"[\[\]\(\)\{\}_\-]+", " ", text)

    # Rimuove caratteri strani
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Spazi multipli
    text = re.sub(r"\s+", " ", text).strip()

    return text


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def clean_filename(name):
    # Caratteri non consentiti da Windows
    name = re.sub(r'[<>:"/\\|?*]', "", name)

    # Evita punti/spazi finali
    name = name.rstrip(" .")

    return name


def search_youtube(query):
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
            errors="replace"
        )

        if result.returncode != 0:
            print("Errore nella ricerca:")
            print(result.stderr)
            return []

        data = json.loads(result.stdout)

        return data.get("entries", [])

    except Exception as e:
        print(f"Errore: {e}")
        return []


def score_result(query, result):
    title = result.get("title", "")
    uploader = result.get("uploader", "") or result.get("channel", "")

    # Confronto con l'intera query
    full_score = similarity(query, title)

    # Estrae artista e titolo dalla query
    parts = query.split(" - ", 1)

    artist_score = 0
    title_score = 0

    if len(parts) == 2:
        artist = parts[0]
        track = parts[1]

        artist_score = similarity(artist, uploader)
        title_score = similarity(track, title)

    # Parole importanti per remix/versioni
    version_words = [
        "remix",
        "mix",
        "extended",
        "edit",
        "vocal",
        "dub",
        "club",
        "radio",
        "rework",
        "bootleg",
        "instrumental",
        "original",
        "remaster",
    ]

    query_norm = normalize(query)
    title_norm = normalize(title)

    version_bonus = 0

    for word in version_words:
        if word in query_norm:
            if word in title_norm:
                version_bonus += 0.08
            else:
                version_bonus -= 0.04

    score = (
        full_score * 0.35
        + artist_score * 0.30
        + title_score * 0.35
        + version_bonus
    )

    return score


def choose_result(query, results):
    scored = []

    for result in results:
        score = score_result(query, result)

        scored.append(
            (
                score,
                result
            )
        )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return scored


def download(url, filename):
    temp_template = os.path.join(
        OUTPUT_DIR,
        "TEMP_%(id)s.%(ext)s"
    )

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

        "--embed-metadata",
        "--embed-thumbnail",

        "--no-playlist",

        "-o",
        temp_template,
    ]

    print("\nDownload in corso...\n")

    result = subprocess.run(command)

    if result.returncode != 0:
        print("ERRORE durante il download.")
        return False

    # Cerca il file temporaneo creato
    for file in os.listdir(OUTPUT_DIR):

        if file.startswith("TEMP_") and file.lower().endswith(".mp3"):

            old_path = os.path.join(
                OUTPUT_DIR,
                file
            )

            new_path = os.path.join(
                OUTPUT_DIR,
                filename
            )

            os.replace(
                old_path,
                new_path
            )

            return True

    return False


def main():

    if not os.path.exists(INPUT_FILE):
        print(f"ERRORE: non trovo {INPUT_FILE}")
        input("Premi INVIO per uscire...")
        return

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        tracks = [
            line.strip()
            for line in f
            if line.strip()
        ]

    total = len(tracks)

    print(f"Trovate {total} tracce.")
    print()

    for index, query in enumerate(tracks, start=1):

        print()
        print("=" * 70)
        print(f"[{index}/{total}] {query}")
        print("=" * 70)

        # Nome finale basato ESATTAMENTE sul TXT
        filename = clean_filename(
            f"{index:02d} - {query}.mp3"
        )

        final_path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        # Se esiste già, salta
        if os.path.exists(final_path):
            print("Gia scaricato. Salto.")
            continue

        print("Cerco su YouTube...")

        results = search_youtube(query)

        if not results:
            print("NESSUN RISULTATO.")
            continue

        scored = choose_result(
            query,
            results
        )

        print()
        print("RISULTATI:")

        for position, (score, result) in enumerate(
            scored,
            start=1
        ):

            title = result.get(
                "title",
                "Titolo sconosciuto"
            )

            uploader = result.get(
                "uploader",
                result.get("channel", "")
            )

            print(
                f"{position}. "
                f"{title} | "
                f"{uploader} | "
                f"score {score:.2f}"
            )

        best_score, best = scored[0]

        title = best.get(
            "title",
            "Titolo sconosciuto"
        )

        uploader = best.get(
            "uploader",
            best.get("channel", "")
        )

        url = best.get("webpage_url")

        if not url:
            video_id = best.get("id")

            if video_id:
                url = (
                    "https://www.youtube.com/watch?v="
                    + video_id
                )

        print()
        print("SCELTO:")
        print(f"Titolo : {title}")
        print(f"Canale : {uploader}")
        print(f"Score  : {best_score:.2f}")
        print(f"URL    : {url}")

        # Se la corrispondenza è molto bassa,
        # non scarica automaticamente
        if best_score < 0.45:

            print()
            print(
                "ATTENZIONE: corrispondenza bassa."
            )

            choice = input(
                "Scaricare comunque? [s/N]: "
            ).strip().lower()

            if choice != "s":
                print("Saltato.")
                continue

        success = download(
            url,
            filename
        )

        if success:
            print()
            print(f"OK -> {filename}")
        else:
            print()
            print("Download fallito.")

    print()
    print("=" * 70)
    print("OPERAZIONE COMPLETATA")
    print("=" * 70)

    input("\nPremi INVIO per chiudere...")


if __name__ == "__main__":
    main()