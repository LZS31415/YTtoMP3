"""YouTube: single videos, playlists, Mix links and chapter splitting."""

from __future__ import annotations

import os

import yt_dlp
from yt_dlp.postprocessor import FFmpegSplitChaptersPP

from .common import ARCHIVE_NAME, Stats, counting_hook, find_js_runtime, progress_hook
from .links import single_video_url, youtube_kind


# --------------------------------------------------------------------------- #
# Playlist / Mix choice
# --------------------------------------------------------------------------- #

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
# Chapter splitting
# --------------------------------------------------------------------------- #

def chapter_folder_template(out_dir: str) -> str:
    return os.path.join(out_dir, "%(title)s", "%(section_number)02d - %(section_title)s.%(ext)s")


def retag(path: str, title: str, album: str | None, track: str) -> None:
    """Give a chapter its own title/track number; keeps artist and cover art."""
    from mutagen.easyid3 import EasyID3
    tags = EasyID3(path)
    tags["title"] = title
    if album:
        tags["album"] = album
    tags["tracknumber"] = track
    tags.save()


class SplitIntoSongsPP(FFmpegSplitChaptersPP):
    """Splits a long video at its chapter timestamps, one MP3 per chapter.

    yt-dlp's own splitter copies the whole video's tags into every piece, so a
    music player would show 30 songs all called "Top Hits Compilation 2026".
    This retags each piece with its chapter title, the video title as album,
    and a track number, then deletes the long file it was cut from.
    """

    def __init__(self, downloader, stats: Stats):
        super().__init__(downloader)
        self.stats = stats

    def run(self, info):
        files_to_delete, info = super().run(info)
        pieces = [c for c in (info.get("chapters") or [])
                  if c.get("filepath") and os.path.exists(c["filepath"])]
        if len(pieces) < 2:
            return files_to_delete, info  # nothing split: keep the full file

        total = len(pieces)
        for n, chapter in enumerate(pieces, 1):
            try:
                retag(chapter["filepath"], chapter.get("title") or f"Track {n}",
                      info.get("title"), f"{n}/{total}")
            except Exception as e:  # tags are cosmetic, the audio is already there
                print(f"  (could not tag {os.path.basename(chapter['filepath'])}: {e})")
        self.stats.songs += total
        print(f"  Split into {total} songs in: {os.path.dirname(pieces[0]['filepath'])}")
        return files_to_delete + [info["filepath"]], info


def decide_split(chapters: list, split: bool | None) -> bool:
    if split is not None:
        return split
    names = [c.get("title") or "?" for c in chapters[:3]]
    print(f"  This video has {len(chapters)} chapters, e.g. " + " | ".join(names))
    answer = input("  Save [1] one MP3 per chapter, or [2] one long MP3? (Enter = 1): ").strip()
    return answer != "2"


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #

def build_options(out_dir: str, quality: str, whole_list: bool, stats: Stats) -> dict:
    opts = {
        "format": "bestaudio/best",
        # "3 - Title.mp3" inside playlists, "Title.mp3" for single songs
        "outtmpl": {
            "default": os.path.join(out_dir, "%(playlist_index&{} - |)s%(title)s.%(ext)s"),
            "chapter": chapter_folder_template(out_dir),  # used only when splitting
        },
        "windowsfilenames": True,
        "noplaylist": not whole_list,
        "lazy_playlist": True,          # start downloading song 1 before the whole list is read
        "download_archive": os.path.join(out_dir, ARCHIVE_NAME),  # skip songs already downloaded
        "ignoreerrors": True,           # skip private/removed videos instead of stopping
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [counting_hook(stats)],
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


def download(url: str, out_dir: str, quality: str, want_all: bool | None,
             split: bool | None = None) -> bool:
    url, whole_list = resolve_choice(url, youtube_kind(url), want_all)
    os.makedirs(out_dir, exist_ok=True)
    print(f"  {'Downloading playlist' if whole_list else 'Downloading'}: {url}")
    if whole_list:
        print("  (Songs already in the folder are skipped. Large lists take a while.)")

    stats = Stats()
    with yt_dlp.YoutubeDL(build_options(out_dir, quality, whole_list, stats)) as ydl:
        if whole_list:
            # Asking per video would interrupt a long playlist, so playlists
            # only split when --split was given.
            if split:
                ydl.add_post_processor(SplitIntoSongsPP(ydl, stats), when="post_process")
            ydl.download([url])
        else:
            # Read the video's details first so we can see its chapters, then download.
            info = ydl.extract_info(url, download=False, process=False)
            if info:
                chapters = info.get("chapters") or []
                if len(chapters) >= 2 and decide_split(chapters, split):
                    ydl.add_post_processor(SplitIntoSongsPP(ydl, stats), when="post_process")
                ydl.process_ie_result(info, download=True)

    if stats.songs:
        print(f"  Done: {stats.songs} songs saved under {out_dir}")
        return True
    if stats.done:
        print(f"  Done: {stats.done} new MP3(s) in {out_dir}")
        return True
    print("  Nothing new was downloaded. Either it was already in the folder, or the video "
          "is private/blocked. Run setup.bat to update yt-dlp, then try again.")
    return False
