# YouTube / TikTok / Douyin to MP3

Paste a link, or the whole share text from the TikTok or Douyin app, and get MP3s with title, artist and cover art. One program for all three sites: single videos, whole playlists, and long compilation videos split into one MP3 per song. Keep pasting while it downloads: every link joins a queue.

## Quick start (Windows)

1. Double-click `setup.bat` once. It installs yt-dlp, the Deno JavaScript runtime, browser impersonation support and ffmpeg if missing.
2. Double-click `download.bat`, paste a link, press Enter. Paste the next one straight away, no need to wait. Press Enter on an empty line to quit once the queue is done.

Everything is saved to `Downloads/Music Downloads`. Use `-o <folder>` to pick another folder.

### The queue

Each link is queued the moment you paste it, and one background worker downloads them in the order you pasted. While it runs you can type:

| Type | What it does |
|---|---|
| a link, several links, or share text | Adds them to the queue |
| `status` | Shows what is downloading, how many are waiting, and how many finished |
| `split auto` | Split YouTube videos into songs only when they look like compilations (default) |
| `split on` / `split off` | Always / never split YouTube videos that have chapters |
| Enter on an empty line | Finishes the queue, then closes. Ctrl+C stops immediately |

The same link pasted twice in one session is only downloaded once.

## What it handles

| You paste | What it does |
|---|---|
| YouTube video (`watch?v=...`, `youtu.be/...`, Shorts, YouTube Music) | Downloads that song |
| YouTube playlist (`playlist?list=...`) | Downloads the whole playlist as `1 - Title.mp3`, `2 - Title.mp3`, ... |
| A YouTube song opened from a playlist or Mix (`watch?v=...&list=...`) | Asks: just this song, or the whole list (Enter = just the song) |
| A YouTube compilation with chapters (timestamps) | Splits it into one MP3 per song automatically (see below) |
| TikTok video, `vt.tiktok.com` short link, profile or collection | Downloads the audio as `Creator - Caption.mp3` |
| Douyin video or image post, `v.douyin.com` share link | Downloads the audio (the background music for image posts) |
| The raw share text from the TikTok/Douyin app, Chinese and hashtags included | Finds the link inside it |
| Several links in one paste, any mix of sites | Handles each in turn |
| Soda Music (`qishui.douyin.com`) | Explains why it isn't supported (see below) |

Split songs go into a folder named after the video, as `01 - Song.mp3`, `02 - Song.mp3`, ..., each tagged with its own title, the video title as album, and a track number. Anything already downloaded is skipped, so re-running a playlist or profile only fetches what is new.

### Command line

```
python downloader.py <link or share text> [...]
python downloader.py --all <url>      # YouTube song from a playlist/Mix: download the whole list
python downloader.py --split <url>    # YouTube: split chapters into separate MP3s (also applies to playlists)
python downloader.py -b firefox <url> # Douyin/TikTok: borrow cookies from this browser
python downloader.py -q 320 -o D:\Music <url>
```

On the command line there is no queue: it runs the links in order and exits. It never stops to ask: it downloads just the song and does not split, unless you pass `--all` or `--split`.

## How it works

```
pasted text ─► find links ─► YouTube ─► yt-dlp ─┬─ playlist / Mix choice ─┬─► MP3 + tags + cover
                         │                      └─ chapters? split + retag ┘
                         ├─► TikTok  ─► yt-dlp ─► clean caption into a title ─► MP3 + tags + cover
                         └─► Douyin  ─► share page resolver ─► ffmpeg ─► MP3 + tags + cover
                                       (no data? escalate cookies: revisit ► visitor token ► browser)
```

Code layout:

```
downloader.py        entry point: reads links, asks any question at paste time, queues jobs
mp3tool/links.py     finds links in pasted text and works out the site
mp3tool/youtube.py   playlists, Mix handling, chapter splitting
mp3tool/tiktok.py    TikTok via yt-dlp, caption cleanup
mp3tool/douyin.py    Douyin share page resolver and cookie escalation
mp3tool/common.py    folders, archive, ffmpeg conversion, JS runtime, progress
```

## Design notes

**YouTube**

- **YouTube now requires a JavaScript runtime.** Before handing out audio, YouTube makes clients solve a JavaScript challenge. Without a runtime, yt-dlp loses formats and eventually fails. `setup.bat` installs Deno through pip, so there is no Node.js install or PATH change to go wrong.
- **Mix links are a trap.** Copying the link of a song playing in a Mix gives `&list=RD...`, an auto-generated list of 25 to 50 songs. The tool spots this and asks instead of silently downloading the lot.
- **Splitting decides itself.** A question in the middle of a download would collide with the next link you are pasting, so the queue decides: a video is split when it is at least 10 minutes long with 3 or more chapters of song length (median 90 seconds or more). Music videos often have chapters too ("Intro", "Chorus"), and cutting those into 20-second pieces would ruin the song. `split on` / `split off` override it.
- **Chapters need retagging.** yt-dlp's chapter splitter copies the whole video's tags into every piece, so a music player would show 30 tracks with the same name. Each piece gets its own title and track number, and the long file is removed only when the split actually produced songs.
- **Start fast.** Playlists are read lazily, so song 1 starts downloading before the whole list has been read.

**Douyin**

- **Why Douyin has its own path.** yt-dlp's Douyin extractor needs fresh browser cookies and doesn't recognise `v.douyin.com` share links, which is what people actually copy from the app. Douyin's mobile share page embeds the post's metadata, so the tool resolves the link, reads that page and downloads the media directly. The parser looks for the post object by shape, not a fixed JSON path, because Douyin reshuffles that structure often.
- **The cookie wall.** Douyin serves the share page to cookie-less requests with the post data stripped out. The resolver escalates only as far as it needs to and keeps whatever worked for the rest of the session: visit again keeping any cookies Douyin set, then register an anonymous visitor token (`ttwid`) the way Douyin's web app does, then borrow Douyin cookies from Firefox, Edge or Chrome. If all three fail, the page Douyin returned is saved to `_debug/` so the failure can be diagnosed instead of guessed at.

**Soda Music is deliberately out of scope.** Soda Music (汽水音乐) share links live on a Douyin domain but are a separate, licensed music service. Its web page only plays a short preview and sends you to the app for the full song, and downloading is a paid VIP feature. Fetching the full file anyway would mean working around that paywall, so the tool says so and suggests a YouTube or Douyin link instead.

**General**

- **Paste anything.** People copy the whole share blob, not a clean URL, so finding links is the first step, not an afterthought.
- **One bad link never ends the session.** Every link is handled on its own; a failure prints a reason and the queue moves on.
- **Questions at paste time, downloads in the background.** The only question left, "just this song or the whole Mix?", depends on the link alone, so it is asked the moment you paste. One worker downloads in order: it avoids hitting a site with parallel requests and keeps the "already downloaded" list consistent. Progress bars are switched off in queue mode because they rewrite the line you are typing on; each download prints whole lines instead.
- **Batch file safety.** The scripts avoid `if (...)` blocks entirely. A `)` inside an `echo` in such a block silently ends it and crashes the script, and `%errorlevel%` inside a block is read before the block runs. Both bit earlier versions.

## Known limitations

- You get the video's audio track. If the creator talks over the music, that is in the MP3 too.
- Douyin changes its pages and anti-bot rules without notice. If the visitor token stops working, open douyin.com once in Firefox and run again. Firefox is the most reliable browser to borrow from on Windows because Chrome and Edge encrypt their cookies in a way that often cannot be read.
- Douyin profile downloads are not supported; they need signed API requests.
- Keep yt-dlp current (`setup.bat` upgrades it). Most YouTube and TikTok breakages are fixed upstream within days.

## Tests

```
python -m unittest discover tests
```

Offline tests cover the queue (paste order, adding while busy, duplicates, a crashing job not stopping the worker, typed commands), the compilation check, link detection across all three sites (including mixed pastes and Soda Music), YouTube link shapes, the Douyin parser against a captured real share page, the cookie escalation logic, ffmpeg conversion with cover art, and the real yt-dlp + ffmpeg pipeline on local files, including a 3-chapter split with per-song tags.

## Disclaimer

For personal use with content you have the right to download. Respect creators and platform terms.
