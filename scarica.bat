@echo off
setlocal enabledelayedexpansion

if not exist "Musica" mkdir "Musica"

set /a n=0

for /f "usebackq delims=" %%A in ("playlist.txt") do (
    set /a n+=1

    echo.
    echo ============================================
    echo [!n!] %%A
    echo ============================================

    yt-dlp ^
        --extractor-args "youtube:player_client=android" ^
        -f "bestaudio/best" ^
        -x ^
        --audio-format mp3 ^
        --audio-quality 0 ^
        --embed-metadata ^
        --embed-thumbnail ^
        --no-playlist ^
        "ytsearch1:%%A" ^
        -o "Musica/!n! - %%(title)s.%%(ext)s"
)

echo.
echo ============================================
echo DOWNLOAD COMPLETATO
echo ============================================
pause