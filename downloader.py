"""
YouTube / TikTok / Douyin to MP3

Paste a link, several links, or the whole share text from the TikTok/Douyin
app, and get tagged MP3s with cover art.

  YouTube  video, playlist, a song opened from a playlist or Mix (asks: just
           this song or the whole list), and compilation videos with chapters
           (asks: one MP3 per chapter or one long MP3).
           Saved to Downloads/YouTube Music.
  TikTok   video, short link, profile, collection.
  Douyin   video and image posts, v.douyin.com share links, raw share text.
           TikTok and Douyin are saved to Downloads/TikTok Music.

Usage:
  python downloader.py                       (interactive, paste links one by one)
  python downloader.py <link or share text> [...]
  python downloader.py --all <url>           (YouTube: whole playlist/Mix without asking)
  python downloader.py --split <url>         (YouTube: one MP3 per chapter)
  python downloader.py -b firefox <url>      (Douyin/TikTok: borrow cookies from this browser)
"""

from __future__ import annotations

import argparse
import shutil
import sys

# Song titles in Chinese, Korean, emoji etc. must never crash the Windows console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

try:
    import yt_dlp  # noqa: F401
except ImportError:
    print("yt-dlp not found. Please run setup.bat first.")
    sys.exit(1)

from mp3tool import douyin, tiktok, youtube
from mp3tool.common import DEFAULT_FOLDERS, find_js_runtime
from mp3tool.links import extract_links

NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "douyin": "Douyin", "soda": "Soda Music"}
SODA_MESSAGE = (
    "  Soda Music (汽水音乐) links aren't supported. Its web page only plays a short "
    "preview, and full-song downloads are a paid VIP feature in the app. If the song "
    "is in a YouTube or Douyin video, paste that link instead."
)


class Session:
    """Settings for one run, plus state worth keeping between links
    (the Douyin cookie jar, so later Douyin links skip the cookie dance)."""

    def __init__(self, args, interactive: bool):
        self.output = args.output
        self.quality = args.quality
        self.browser = args.browser
        # On the command line nothing may stop to ask, so unanswered
        # questions get the safe default: just the song, no splitting.
        self.want_all = args.want_all if (interactive or args.want_all is not None) else False
        self.split = args.split if (interactive or args.split is not None) else False
        self._douyin_client = None

    def folder(self, platform: str) -> str:
        return self.output or DEFAULT_FOLDERS[platform]

    @property
    def douyin_client(self) -> douyin.DouyinClient:
        if self._douyin_client is None:
            self._douyin_client = douyin.DouyinClient(self.browser)
        return self._douyin_client

    def process(self, platform: str, url: str) -> bool:
        print(f"\n[{NAMES[platform]}] {url}")
        if platform == "soda":
            print(SODA_MESSAGE)
            return False
        try:
            if platform == "youtube":
                return youtube.download(url, self.folder("youtube"), self.quality, self.want_all, self.split)
            if platform == "tiktok":
                return tiktok.download(url, self.folder("tiktok"), self.quality, self.browser)
            return douyin.download(url, self.folder("douyin"), self.quality, self.douyin_client)
        except Exception as e:  # one bad link must never end the session
            print(f"  Failed: {e}")
            return False


def check_setup() -> None:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Run setup.bat, then close and reopen this window.")
        sys.exit(1)
    if not find_js_runtime():
        print("WARNING: no JavaScript runtime found, so YouTube may refuse some downloads. "
              "Run setup.bat to fix this.\n")


def run_text(session: Session, text: str) -> tuple[int, int]:
    """Process every link in the text. Returns (ok, failed)."""
    links = extract_links(text)
    if not links:
        print("  No YouTube, TikTok or Douyin link found in that text.")
        return 0, 1
    ok = sum(session.process(p, u) for p, u in links)
    return ok, len(links) - ok


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Download YouTube, TikTok and Douyin audio as MP3.")
    parser.add_argument("links", nargs="*", help="links or pasted share text")
    parser.add_argument("-o", "--output", default=None,
                        help="output folder (default: Downloads/YouTube Music or Downloads/TikTok Music)")
    parser.add_argument("-q", "--quality", default="192", choices=["128", "192", "256", "320"],
                        help="MP3 bitrate in kbps (default 192)")
    parser.add_argument("-b", "--browser", default=None,
                        help="browser to borrow cookies from if Douyin/TikTok need them (firefox, edge, chrome)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", dest="want_all", action="store_const", const=True,
                       help="YouTube: for a song opened from a playlist/Mix, download the whole list")
    group.add_argument("--single", dest="want_all", action="store_const", const=False,
                       help="YouTube: for a song opened from a playlist/Mix, download only that song")
    split_group = parser.add_mutually_exclusive_group()
    split_group.add_argument("--split", dest="split", action="store_const", const=True,
                             help="YouTube: split videos with chapters into one MP3 per chapter")
    split_group.add_argument("--no-split", dest="split", action="store_const", const=False,
                             help="YouTube: never split, and don't ask")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    check_setup()

    if args.links:
        session = Session(args, interactive=False)
        ok, failed = run_text(session, " ".join(args.links))
        print(f"\nFinished: {ok} OK, {failed} failed.")
        sys.exit(1 if failed else 0)

    session = Session(args, interactive=True)
    if args.output:
        print(f"Saving to: {args.output}")
    else:
        print(f"YouTube saves to: {DEFAULT_FOLDERS['youtube']}")
        print(f"TikTok/Douyin save to: {DEFAULT_FOLDERS['tiktok']}")
    while True:
        try:
            text = input("\nPaste a YouTube, TikTok or Douyin link (or share text), "
                         "or press Enter to quit: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        run_text(session, text)


if __name__ == "__main__":
    main()
