"""
YouTube Video / Playlist to MP3 Downloader

Paste a YouTube link and get MP3s in Downloads/YouTube Music.
  - A video link downloads that song.
  - A playlist link (youtube.com/playlist?list=...) downloads the whole playlist.
  - A video opened from a playlist or Mix (watch?v=...&list=...) asks whether you
    want just that song or the whole list.

Usage:
  python downloader.py                      (interactive, paste links one by one)
  python downloader.py <url> [<url> ...]
  python downloader.py --all <url>          (whole playlist/Mix without asking)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from urllib.parse import parse_qs, urlparse

try:
    import yt_dlp
except ImportError:
    print("yt-dlp not found. Please run setup.bat first.")
    sys.exit(1)

# Song titles in Chinese, Korean, emoji etc. must never crash the Windows console.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(errors="replace")
    except Exception:
        pass


DEFAULT_OUTPUT = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube Music")
ARCHIVE_NAME = ".downloaded.txt"
YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "music.youtube.com")


# --------------------------------------------------------------------------- #
# Link handling
# --------------------------------------------------------------------------- #

def is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


def classify(url: str) -> str:
    """'video', 'playlist', 'video_in_playlist' or 'video_in_mix'."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    list_id = (query.get("list") or [""])[0]
    has_video = bool(query.get("v")) or parsed.hostname == "youtu.be" or "/shorts/" in parsed.path
    if not list_id:
        return "video"
    if not has_video:
        return "playlist"
    # RD... lists are auto-generated Mixes / radio: long, and never what you
    # meant if you just copied the link of the song you were listening to.
    return "video_in_mix" if list_id.startswith("RD") else "video_in_playlist"


def single_video_url(url: str) -> str:
    """Strip playlist parameters so only the song itself is downloaded."""
    parsed = urlparse(url)
    if parsed.hostname == "youtu.be":
        return f"https://youtu.be{parsed.path}"
    video_id = parse_qs(parsed.query).get("v", [""])[0]
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else url


def resolve_choice(url: str, kind: str, want_all: bool | None) -> tuple[str, bool]:
    """Return (url_to_download, whole_list)."""
    if kind == "video":
        return url, False
    if kind == "playlist":
        return url, True
    if want_all is None:  # interactive: ask
        label = "a YouTube Mix (auto-generated, usually 25-50 songs)" if kind == "video_in_mix" else "a playlist"
        print(f"  This song was opened from {label}.")
        answer = input("  Download [1] just this song, or [2] the whole list? (Enter = 1): ").strip()
        want_all = answer == "2"
    return (url, True) if want_all else (single_video_url(url), False)


# --------------------------------------------------------------------------- #
# yt-dlp setup
# --------------------------------------------------------------------------- #

def find_js_runtime() -> dict | None:
    """YouTube makes downloaders run a JavaScript challenge before it hands
    out audio. yt-dlp needs a JS runtime for that. setup.bat installs Deno via
    pip, which yt-dlp finds on its own; this just makes the choice explicit and
    falls back to Node.js if that is what the PC has."""
    try:
        import deno
        return {"deno": {"path": deno.find_deno_bin()}}
    except Exception:
        pass
    if shutil.which("deno"):
        return {"deno": {}}
    node = shutil.which("node")
    if node:
        return {"node": {"path": node}}
    return None


class Stats:
    def __init__(self):
        self.done = 0
        self.titles: list[str] = []


def build_options(out_dir: str, quality: str, whole_list: bool, stats: Stats) -> dict:
    def progress_hook(d):
        info = d.get("info_dict", {})
        title = (info.get("title") or "")[:50]
        pos = info.get("playlist_index")
        prefix = f"[{pos}] " if pos else ""
        if d["status"] == "downloading":
            pct = (d.get("_percent_str") or "").strip()
            print(f"\r  {prefix}{title:<50} {pct:>7}", end="", flush=True)
        elif d["status"] == "finished":
            print(f"\r  {prefix}{title:<50} converting...", flush=True)

    def pp_hook(d):
        if d["status"] == "finished" and d.get("postprocessor") == "MoveFiles":
            stats.done += 1
            stats.titles.append(d.get("info_dict", {}).get("title", ""))

    opts = {
        "format": "bestaudio/best",
        # "3 - Title.mp3" inside playlists, "Title.mp3" for single songs
        "outtmpl": os.path.join(out_dir, "%(playlist_index&{} - |)s%(title)s.%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": not whole_list,
        "lazy_playlist": True,          # start downloading song 1 before the whole list is read
        "download_archive": os.path.join(out_dir, ARCHIVE_NAME),  # skip songs already downloaded
        "ignoreerrors": True,           # skip private/removed videos instead of stopping
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [pp_hook],
        "writethumbnail": True,
        "postprocessors": [
            # YouTube thumbnails are WebP, which many MP3 players can't show: convert first
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
    }
    runtime = find_js_runtime()
    if runtime:
        opts["js_runtimes"] = runtime
    return opts


# --------------------------------------------------------------------------- #
# Main flow
# --------------------------------------------------------------------------- #

def download(url: str, out_dir: str, quality: str, want_all: bool | None) -> bool:
    url, whole_list = resolve_choice(url, classify(url), want_all)
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n{'Downloading playlist' if whole_list else 'Downloading'}: {url}")
    if whole_list:
        print("  (Songs already in the folder are skipped. Large lists take a while.)")

    stats = Stats()
    with yt_dlp.YoutubeDL(build_options(out_dir, quality, whole_list, stats)) as ydl:
        ydl.download([url])

    if stats.done:
        print(f"\nDone: {stats.done} new MP3(s) in {out_dir}")
        return True
    print("\nNothing new was downloaded. Either it was already in the folder, or the video "
          "is private/blocked. Run setup.bat to update yt-dlp, then try again.")
    return False


def check_setup() -> None:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Run setup.bat, then close and reopen this window.")
        sys.exit(1)
    if not find_js_runtime():
        print("WARNING: no JavaScript runtime found, so YouTube may refuse some downloads. "
              "Run setup.bat to fix this.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download YouTube videos or playlists as MP3.")
    parser.add_argument("urls", nargs="*")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    parser.add_argument("-q", "--quality", default="192", choices=["128", "192", "256", "320"])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", dest="want_all", action="store_const", const=True,
                       help="for a song opened from a playlist/Mix, download the whole list")
    group.add_argument("--single", dest="want_all", action="store_const", const=False,
                       help="for a song opened from a playlist/Mix, download only that song")
    args = parser.parse_args()

    check_setup()

    if args.urls:
        want_all = False if args.want_all is None else args.want_all  # never block on input()
        failed = 0
        for url in args.urls:
            if not is_youtube(url):
                print(f"Skipping (not a YouTube link): {url}")
                failed += 1
                continue
            failed += not download(url, args.output, args.quality, want_all)
        sys.exit(1 if failed else 0)

    print(f"Saving to: {args.output}")
    while True:
        try:
            url = input("\nPaste a YouTube link (video or playlist), or press Enter to quit: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not url:
            break
        if not is_youtube(url):
            print("  That doesn't look like a YouTube link.")
            continue
        download(url, args.output, args.quality, args.want_all)


if __name__ == "__main__":
    main()
