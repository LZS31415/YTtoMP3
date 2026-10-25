"""Helpers shared by every source: folders, titles, the download archive,
ffmpeg conversion, the JavaScript runtime and progress output."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
DEFAULT_FOLDER = os.path.join(DOWNLOADS, "Music Downloads")  # every site saves here
ARCHIVE_NAME = ".downloaded.txt"  # yt-dlp's format: "<extractor> <id>" per line
MAX_TITLE_CHARS = 60


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

_print_lock = threading.Lock()
# Live progress bars rewrite the current line with "\r". That is fine when
# downloads run one at a time, but in queue mode the user is typing on that
# line, so the queue switches them off and only whole lines are printed.
LIVE_PROGRESS = True


def say(message: str = "") -> None:
    """Print one whole line, safely from any thread."""
    with _print_lock:
        print(message, flush=True)


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #

def clean_title(text: str | None, fallback: str) -> str:
    """Turn a TikTok/Douyin caption into a usable song title: drop hashtags
    and @mentions, collapse spaces, trim to a sane length."""
    text = text or ""
    text = re.sub(r"[#＃]\S+", " ", text)
    text = re.sub(r"@\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -_|·")
    if len(text) > MAX_TITLE_CHARS:
        text = text[:MAX_TITLE_CHARS].rstrip() + "…"
    return text or fallback


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(" .") or "untitled"


def unique_path(path: str, suffix_id: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    return f"{base} ({suffix_id}){ext}"


# --------------------------------------------------------------------------- #
# Download archive (skip things already downloaded)
# --------------------------------------------------------------------------- #

def archive_path(out_dir: str) -> str:
    return os.path.join(out_dir, ARCHIVE_NAME)


def in_archive(out_dir: str, key: str) -> bool:
    try:
        with open(archive_path(out_dir), encoding="utf-8") as f:
            return any(line.strip() == key for line in f)
    except FileNotFoundError:
        return False


def add_to_archive(out_dir: str, key: str) -> None:
    with open(archive_path(out_dir), "a", encoding="utf-8") as f:
        f.write(key + "\n")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

def find_js_runtime() -> dict | None:
    """YouTube makes downloaders solve a JavaScript challenge before it hands
    out audio, so yt-dlp needs a JS runtime. setup.bat installs Deno via pip;
    this makes the choice explicit and falls back to Node.js if present."""
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


def convert_to_mp3(src: str, dest: str, title: str, artist: str, quality: str,
                   cover: str | None = None, source_url: str = "") -> None:
    """ffmpeg: any audio/video in -> tagged MP3 (with cover art if we have it)."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src]
    if cover:
        cmd += ["-i", cover, "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg",
                "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
    else:
        cmd += ["-map", "0:a", "-vn"]
    cmd += ["-c:a", "libmp3lame", "-b:a", f"{quality}k", "-id3v2_version", "3",
            "-metadata", f"title={title}", "-metadata", f"artist={artist}",
            "-metadata", f"comment={source_url}", dest]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 and cover:
        # A weird cover format should not cost us the song: retry without it.
        return convert_to_mp3(src, dest, title, artist, quality, None, source_url)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-300:]}")


# --------------------------------------------------------------------------- #
# Progress output shared by the yt-dlp based sources
# --------------------------------------------------------------------------- #

class Stats:
    def __init__(self):
        self.done = 0    # items fully processed into an MP3
        self.songs = 0   # MP3s created by chapter splitting


def progress_hook(d):
    if not LIVE_PROGRESS:
        return
    info = d.get("info_dict", {})
    title = (info.get("title") or "")[:50]
    pos = info.get("playlist_index")
    prefix = f"[{pos}] " if pos else ""
    if d["status"] == "downloading":
        pct = (d.get("_percent_str") or "").strip()
        with _print_lock:
            print(f"\r  {prefix}{title:<50} {pct:>7}", end="", flush=True)
    elif d["status"] == "finished":
        with _print_lock:
            print(f"\r  {prefix}{title:<50} converting...", flush=True)


def counting_hook(stats: Stats):
    def hook(d):
        if d["status"] == "finished" and d.get("postprocessor") == "MoveFiles":
            stats.done += 1
    return hook
