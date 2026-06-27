"""
YouTube Playlist/Video to MP3 Downloader
Downloads all videos from a YouTube playlist (or single video) as MP3 files
into your Downloads folder.
"""

import sys
import os
import re

try:
    import yt_dlp
except ImportError:
    print("yt-dlp not found. Please run setup.bat first.")
    sys.exit(1)


DOWNLOADS_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube Music")


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def find_node() -> str | None:
    """Return the path to node.exe if installed, else None."""
    import shutil
    node = shutil.which("node")
    if node:
        return node
    # Common winget install location
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidate = os.path.join(local_app, "Programs", "nodejs", "node.exe")
    return candidate if os.path.isfile(candidate) else None


def download(url: str):
    os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOADS_FOLDER, "%(playlist_index)s - %(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "ignoreerrors": True,       # skip unavailable videos
        "quiet": False,
        "no_warnings": False,
        "progress_hooks": [progress_hook],
    }

    # Point yt-dlp at Node.js so YouTube extraction works without warnings
    node_path = find_node()
    if node_path:
        ydl_opts["extractor_args"] = {"youtube": {"player_client": ["web"]}}
        # Pass node path via environment so yt-dlp's JS runner can find it
        os.environ.setdefault("PATH", "")
        node_dir = os.path.dirname(node_path)
        if node_dir not in os.environ["PATH"]:
            os.environ["PATH"] = node_dir + os.pathsep + os.environ["PATH"]
    else:
        print("WARNING: Node.js not found. Run setup.bat to install it for best results.\n")

    # For single videos (not playlists), skip the playlist index prefix
    with yt_dlp.YoutubeDL({"quiet": True}) as probe:
        try:
            info = probe.extract_info(url, download=False)
            is_playlist = info.get("_type") == "playlist" or "entries" in info
        except Exception:
            is_playlist = False

    if not is_playlist:
        ydl_opts["outtmpl"] = os.path.join(DOWNLOADS_FOLDER, "%(title)s.%(ext)s")

    print(f"\nOutput folder: {DOWNLOADS_FOLDER}\n")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    print(f"\nDone! Files saved to: {DOWNLOADS_FOLDER}")


def progress_hook(d):
    if d["status"] == "finished":
        print(f"  Converting: {os.path.basename(d['filename'])}")
    elif d["status"] == "downloading":
        title = d.get("info_dict", {}).get("title", "")
        percent = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        print(f"\r  Downloading: {title[:50]:<50} {percent:>7}  {speed:>12}  ETA {eta}", end="", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        url = input("Enter YouTube URL (video or playlist): ").strip()
    else:
        url = sys.argv[1].strip()

    if not url:
        print("No URL provided.")
        sys.exit(1)

    download(url)
