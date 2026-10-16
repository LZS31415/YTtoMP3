# YouTube to MP3

Paste a YouTube link, get MP3s with title, artist and cover art in `Downloads/YouTube Music`. Works for single videos, whole playlists, and long compilation videos, which it can split into one MP3 per song.

Sister project: [ttdytomp3](https://github.com/LZS31415/ttdytomp3) (TikTok / Douyin to MP3).

## Quick start (Windows)

1. Double-click `setup.bat` once. It installs yt-dlp, the Deno JavaScript runtime and ffmpeg if missing.
2. Double-click `download.bat`, paste a link, press Enter. Paste another, or press Enter on an empty line to quit.

## What happens with each kind of link

| You paste | What it does |
|---|---|
| A video (`watch?v=...`, `youtu.be/...`, Shorts) | Downloads that song |
| A playlist (`playlist?list=...`) | Downloads the whole playlist as `1 - Title.mp3`, `2 - Title.mp3`, ... |
| A song you opened from a playlist or Mix (`watch?v=...&list=...`) | Asks: just this song, or the whole list (Enter = just the song) |
| A compilation video with chapters (timestamps) | Asks: one MP3 per chapter, or one long MP3 (Enter = split) |

Split songs go into a folder named after the video, as `01 - Song.mp3`, `02 - Song.mp3`, ..., each tagged with its own title, the video title as album, and a track number.

Songs already downloaded are skipped, so re-running a playlist only fetches what is new.

### Command line

```
python downloader.py <url> [<url> ...]
python downloader.py --all <url>      # song from a playlist/Mix: download the whole list
python downloader.py --split <url>    # split chapters into separate MP3s (also applies to playlists)
python downloader.py -q 320 -o D:\Music <url>
```

On the command line it never stops to ask: it downloads just the song and does not split, unless you pass `--all` or `--split`.

## Design notes

- **YouTube now requires a JavaScript runtime.** Before handing out audio, YouTube makes clients solve a JavaScript challenge. Without a runtime, yt-dlp loses formats and eventually fails. `setup.bat` installs Deno through pip (`yt-dlp[default,deno]`), so there is no Node.js install or PATH change to go wrong.
- **Mix links are a trap.** Copying the link of a song playing in a Mix gives `&list=RD...`, an auto-generated list of 25 to 50 songs. The tool spots this and asks instead of silently downloading the lot.
- **Chapters need retagging.** yt-dlp's chapter splitter copies the whole video's tags into every piece, so a music player would show 30 tracks with the same name. Each piece gets its own title and track number, and the long file is removed.
- **Start fast.** Playlists are read lazily, so song 1 starts downloading before the whole list has been read.
- **Batch file safety.** The scripts avoid `if (...)` blocks entirely. A `)` inside an `echo` in such a block silently ends it and crashes the script, which is what broke the first version of `setup.bat`.

## Tests

```
python -m unittest discover tests
```

Offline tests cover link classification, and run the real yt-dlp + ffmpeg pipeline on a local 3-chapter file to check splitting, tagging, skipping already-downloaded songs, and that nothing is lost when a video has no chapters.

## Disclaimer

For personal use with content you have the right to download.
