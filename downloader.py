"""
YouTube / TikTok / Douyin to MP3

Paste links and keep pasting: each one joins a download queue and you can
paste the next straight away. Everything is saved to Downloads/Music Downloads.

  YouTube  video, playlist, a song opened from a playlist or Mix (asks right
           away: just this song or the whole list), and compilation videos,
           which are split into one MP3 per song automatically.
  TikTok   video, short link, profile, collection.
  Douyin   video and image posts, v.douyin.com share links, raw share text.

While it runs, type instead of a link:
  status       what is downloading and what is queued
  split on     always split YouTube videos with chapters into separate songs
  split off    never split
  split auto   split only videos that look like compilations (default)
  (Enter)      quit once the queue is finished

Command line (no queue, runs the links and exits):
  python downloader.py <link or share text> [...]
  python downloader.py --all <url>           (YouTube: whole playlist/Mix without asking)
  python downloader.py --split <url>         (YouTube: one MP3 per chapter)
  python downloader.py -b firefox <url>      (Douyin/TikTok: borrow cookies from this browser)
"""

from __future__ import annotations

import argparse
import queue
import shutil
import sys
import threading
from dataclasses import dataclass

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

from mp3tool import common, douyin, tiktok, youtube
from mp3tool.common import DEFAULT_FOLDER, find_js_runtime, say
from mp3tool.links import extract_links, youtube_kind

NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "douyin": "Douyin", "soda": "Soda Music"}
SODA_MESSAGE = (
    "  Soda Music (汽水音乐) links aren't supported. Its web page only plays a short "
    "preview, and full-song downloads are a paid VIP feature in the app. If the song "
    "is in a YouTube or Douyin video, paste that link instead."
)
SPLIT_NAMES = {True: "on", False: "off", None: "auto"}


@dataclass(frozen=True)
class Job:
    platform: str
    url: str
    whole_list: bool = False   # YouTube only: settled at paste time


class Session:
    """Settings for one run, plus state worth keeping between links
    (the Douyin cookie jar, so later Douyin links skip the cookie dance)."""

    def __init__(self, args, interactive: bool):
        self.output = args.output or DEFAULT_FOLDER
        self.quality = args.quality
        self.browser = args.browser
        # On the command line nothing may stop to ask, so unanswered
        # questions get the safe default: just the song, no splitting.
        self.want_all = args.want_all if (interactive or args.want_all is not None) else False
        if args.split is not None:
            self.split = args.split
        else:
            self.split = None if interactive else False   # None = automatic
        self._douyin_client = None

    @property
    def douyin_client(self) -> douyin.DouyinClient:
        if self._douyin_client is None:
            self._douyin_client = douyin.DouyinClient(self.browser)
        return self._douyin_client

    def prepare(self, platform: str, url: str) -> Job | None:
        """Runs at paste time, on the thread reading input, so any question
        is asked right away instead of interrupting a later download."""
        if platform == "soda":
            say(f"\n[{NAMES[platform]}] {url}")
            say(SODA_MESSAGE)
            return None
        if platform == "youtube":
            url, whole_list = youtube.resolve_choice(url, youtube_kind(url), self.want_all)
            return Job(platform, url, whole_list)
        return Job(platform, url)

    def run(self, job: Job) -> bool:
        try:
            if job.platform == "youtube":
                return youtube.download(job.url, self.output, self.quality, job.whole_list, self.split)
            if job.platform == "tiktok":
                return tiktok.download(job.url, self.output, self.quality, self.browser)
            return douyin.download(job.url, self.output, self.quality, self.douyin_client)
        except Exception as e:  # one bad link must never end the session
            say(f"  Failed: {e}")
            return False


class DownloadQueue:
    """One background worker downloading jobs in the order they were pasted.

    One at a time on purpose: it keeps each site from seeing a burst of
    parallel requests, and keeps the "already downloaded" list consistent.
    """

    def __init__(self, session: Session):
        self.session = session
        self._jobs: queue.Queue[Job] = queue.Queue()
        self._seen: set[Job] = set()
        self._lock = threading.Lock()
        self.current: Job | None = None
        self.ok = self.failed = 0
        self.closing = False   # set once the user pressed Enter to quit
        self._worker = threading.Thread(target=self._work, daemon=True)
        self._worker.start()

    def add(self, job: Job) -> bool:
        with self._lock:
            if job in self._seen:
                return False
            self._seen.add(job)
        self._jobs.put(job)
        return True

    def waiting(self) -> int:
        return self._jobs.qsize()

    def busy(self) -> bool:
        return self.current is not None or self.waiting() > 0

    def wait(self) -> None:
        self._jobs.join()

    def status(self) -> str:
        now = f"downloading {NAMES[self.current.platform]} {self.current.url}" if self.current else "idle"
        return f"  Now: {now}. Queued: {self.waiting()}. Finished: {self.ok} OK, {self.failed} failed."

    def _work(self) -> None:
        while True:
            job = self._jobs.get()
            self.current = job
            say(f"\n[{NAMES[job.platform]}] {job.url}"
                + (f"   ({self.waiting()} more queued)" if self.waiting() else ""))
            try:
                if self.session.run(job):
                    self.ok += 1
                else:
                    self.failed += 1
            finally:
                self.current = None
                if self._jobs.qsize() == 0:
                    tail = "" if self.closing else " Paste more links, or press Enter to quit."
                    say(f"\nQueue empty ({self.ok} OK, {self.failed} failed).{tail}")
                self._jobs.task_done()


def check_setup() -> None:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Run setup.bat, then close and reopen this window.")
        sys.exit(1)
    if not find_js_runtime():
        print("WARNING: no JavaScript runtime found, so YouTube may refuse some downloads. "
              "Run setup.bat to fix this.\n")


def handle_command(text: str, session: Session, jobs: DownloadQueue) -> bool:
    """Typed commands instead of links. Returns True if it was one."""
    cmd = text.strip().lower()
    if cmd == "status":
        say(jobs.status())
        return True
    if cmd in ("split on", "split off", "split auto"):
        session.split = {"on": True, "off": False, "auto": None}[cmd.split()[1]]
        say(f"  Chapter splitting: {SPLIT_NAMES[session.split]} (applies to links pasted from now on).")
        return True
    return False


def queue_text(session: Session, jobs: DownloadQueue, text: str) -> int:
    """Queue every link in the pasted text. Returns how many were queued."""
    links = extract_links(text)
    if not links:
        say("  No YouTube, TikTok or Douyin link found in that text.")
        return 0
    queued = 0
    for platform, url in links:
        job = session.prepare(platform, url)
        if job is None:
            continue
        if jobs.add(job):
            queued += 1
            ahead = jobs.waiting() - 1 + (1 if jobs.current else 0)
            say(f"  Queued {NAMES[platform]} link" + (f" ({ahead} ahead of it)." if ahead > 0 else "."))
        else:
            say("  Already in this session's queue, skipped.")
    return queued


def run_now(session: Session, text: str) -> tuple[int, int]:
    """Command-line mode: process every link in order, no queue. Returns (ok, failed)."""
    links = extract_links(text)
    if not links:
        say("  No YouTube, TikTok or Douyin link found in that text.")
        return 0, 1
    ok = 0
    for platform, url in links:
        job = session.prepare(platform, url)
        if job is not None:
            say(f"\n[{NAMES[platform]}] {url}")
            ok += session.run(job)
    return ok, len(links) - ok


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Download YouTube, TikTok and Douyin audio as MP3.")
    parser.add_argument("links", nargs="*", help="links or pasted share text")
    parser.add_argument("-o", "--output", default=None,
                        help=f"output folder (default: {DEFAULT_FOLDER})")
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
                             help="YouTube: always split videos with chapters into one MP3 per chapter")
    split_group.add_argument("--no-split", dest="split", action="store_const", const=False,
                             help="YouTube: never split")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    check_setup()

    if args.links:
        session = Session(args, interactive=False)
        ok, failed = run_now(session, " ".join(args.links))
        say(f"\nFinished: {ok} OK, {failed} failed.")
        sys.exit(1 if failed else 0)

    session = Session(args, interactive=True)
    common.LIVE_PROGRESS = False   # the user types while downloads run: whole lines only
    jobs = DownloadQueue(session)
    say(f"Saving to: {session.output}")
    say("Paste links one after another, no need to wait. Type 'status' to see the queue,")
    say("'split on' / 'split off' / 'split auto' for compilations, or press Enter to quit.")
    try:
        while True:
            text = input("\n> ").strip()
            if not text:
                break
            if not handle_command(text, session, jobs):
                queue_text(session, jobs, text)
        jobs.closing = True
        if jobs.busy():
            say(f"\nFinishing the queue first ({jobs.waiting() + (1 if jobs.current else 0)} left). "
                "Press Ctrl+C to stop now.")
            jobs.wait()
    except (EOFError, KeyboardInterrupt):
        if jobs.busy():
            say("\nStopped. Unfinished downloads will start again next time you paste them.")


if __name__ == "__main__":
    main()
