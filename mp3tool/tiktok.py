"""TikTok: single videos, short links, profiles and collections via yt-dlp."""

from __future__ import annotations

import os

import yt_dlp
from yt_dlp.postprocessor import PostProcessor

from .common import Stats, archive_path, clean_title, counting_hook, progress_hook


class CleanTitlePP(PostProcessor):
    """Runs before download: replaces the caption with a clean title."""

    def run(self, info):
        info["title"] = clean_title(info.get("title") or info.get("description"), info.get("id", "untitled"))
        if not info.get("uploader"):
            info["uploader"] = info.get("creator") or info.get("uploader_id") or "Unknown"
        return [], info


def build_options(out_dir: str, quality: str, stats: Stats, browser: str | None = None) -> dict:
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "%(uploader)s - %(title)s.%(ext)s"),
        "windowsfilenames": True,
        "writethumbnail": True,
        "download_archive": archive_path(out_dir),
        "ignoreerrors": True,  # one broken video should not stop a whole profile
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [counting_hook(stats)],
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
    }
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def download(url: str, out_dir: str, quality: str, browser: str | None = None) -> bool:
    os.makedirs(out_dir, exist_ok=True)
    stats = Stats()
    with yt_dlp.YoutubeDL(build_options(out_dir, quality, stats, browser)) as ydl:
        ydl.add_post_processor(CleanTitlePP(), when="pre_process")
        errors = ydl.download([url])
    if stats.done:
        print(f"  Done: {stats.done} new MP3(s) in {out_dir}")
        return True
    if errors == 0:
        print("  Nothing new: already in the folder.")
        return True
    print("  Download failed. Run setup.bat to update yt-dlp, then try again.")
    return False
