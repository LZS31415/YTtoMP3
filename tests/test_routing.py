"""Routing and queue tests: pasted links of any site join one download queue."""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import downloader  # noqa: E402
from mp3tool import common, links, youtube  # noqa: E402


class TestLinkDetection(unittest.TestCase):
    def test_mixed_paste(self):
        text = ("https://www.youtube.com/watch?v=abc and "
                "7.43 复制打开抖音，看看【某某的作品】好听 https://v.douyin.com/iABcDeF/ q@E.Ux "
                "https://vt.tiktok.com/ZSabc123/")
        self.assertEqual(links.extract_links(text), [
            ("youtube", "https://www.youtube.com/watch?v=abc"),
            ("douyin", "https://v.douyin.com/iABcDeF/"),
            ("tiktok", "https://vt.tiktok.com/ZSabc123/"),
        ])

    def test_soda_music_is_not_douyin(self):
        self.assertEqual(links.platform_of("https://qishui.douyin.com/s/iXnq975V/"), "soda")
        self.assertEqual(links.platform_of("https://music.douyin.com/qishui/share/track?track_id=1"), "soda")
        self.assertEqual(links.platform_of("https://www.douyin.com/video/1"), "douyin")

    def test_youtube_hosts(self):
        for url in ("https://youtu.be/abc", "https://music.youtube.com/watch?v=abc",
                    "https://m.youtube.com/watch?v=abc", "https://www.youtube.com/shorts/abc"):
            self.assertEqual(links.platform_of(url), "youtube", url)

    def test_lookalike_domains_ignored(self):
        self.assertEqual(links.extract_links("https://evil-tiktok.com.example/x https://notyoutube.com/x"), [])


class TestSession(unittest.TestCase):
    def session(self, argv, interactive):
        return downloader.Session(downloader.parse_args(argv), interactive)

    def test_command_line_never_asks(self):
        s = self.session(["https://youtu.be/abc"], interactive=False)
        self.assertEqual((s.want_all, s.split), (False, False))

    def test_interactive_asks_mix_and_splits_automatically(self):
        s = self.session([], interactive=True)
        self.assertEqual((s.want_all, s.split), (None, None))

    def test_flags_win(self):
        s = self.session(["--all", "--split", "x"], interactive=False)
        self.assertEqual((s.want_all, s.split), (True, True))

    def test_one_folder_for_every_site(self):
        s = self.session([], interactive=True)
        self.assertEqual(s.output, common.DEFAULT_FOLDER)
        self.assertTrue(s.output.endswith("Music Downloads"))
        self.assertEqual(self.session(["-o", "D:/Music"], interactive=True).output, "D:/Music")

    def test_soda_link_is_explained_not_queued(self):
        s = self.session([], interactive=True)
        self.assertIsNone(s.prepare("soda", "https://qishui.douyin.com/s/x/"))

    def test_mix_question_settled_at_paste_time(self):
        s = self.session(["--single"], interactive=True)
        job = s.prepare("youtube", "https://www.youtube.com/watch?v=abc&list=RDabc")
        self.assertEqual(job, downloader.Job("youtube", "https://www.youtube.com/watch?v=abc", False))

    def test_douyin_cookie_jar_reused_across_links(self):
        s = self.session([], interactive=True)
        self.assertIs(s.douyin_client, s.douyin_client)


class FakeSession:
    """Records jobs instead of downloading; can be made slow or to fail."""

    def __init__(self, fail_on=(), gate=None):
        self.done, self.fail_on, self.gate = [], set(fail_on), gate

    def run(self, job):
        if self.gate:
            self.gate.wait(5)
        if job.url in self.fail_on:
            raise RuntimeError("boom")
        self.done.append(job.url)
        return True


class TestQueue(unittest.TestCase):
    def test_runs_in_paste_order(self):
        fake = FakeSession()
        q = downloader.DownloadQueue(fake)
        for i in range(5):
            q.add(downloader.Job("tiktok", f"u{i}"))
        q.wait()
        self.assertEqual(fake.done, [f"u{i}" for i in range(5)])
        self.assertEqual((q.ok, q.failed), (5, 0))

    def test_can_keep_adding_while_busy(self):
        gate = threading.Event()   # holds the first download "in progress"
        fake = FakeSession(gate=gate)
        q = downloader.DownloadQueue(fake)
        q.add(downloader.Job("youtube", "first"))
        q.add(downloader.Job("douyin", "second"))
        q.add(downloader.Job("tiktok", "third"))   # pasted while 'first' still runs
        self.assertTrue(q.busy())
        self.assertEqual(fake.done, [])
        gate.set()
        q.wait()
        self.assertEqual(fake.done, ["first", "second", "third"])

    def test_duplicate_paste_is_ignored(self):
        fake = FakeSession()
        q = downloader.DownloadQueue(fake)
        self.assertTrue(q.add(downloader.Job("tiktok", "same")))
        self.assertFalse(q.add(downloader.Job("tiktok", "same")))
        q.wait()
        self.assertEqual(fake.done, ["same"])

    def test_crash_in_one_job_does_not_stop_the_worker(self):
        session = downloader.Session(downloader.parse_args([]), interactive=True)
        original = downloader.tiktok.download
        downloader.tiktok.download = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            q = downloader.DownloadQueue(session)
            q.add(downloader.Job("tiktok", "bad"))
            q.wait()
        finally:
            downloader.tiktok.download = original
        fake = FakeSession()
        q.session = fake
        q.add(downloader.Job("tiktok", "good"))
        q.wait()
        self.assertEqual((q.failed, fake.done), (1, ["good"]))

    def test_queue_text_queues_every_link_in_a_paste(self):
        fake = FakeSession()
        session = downloader.Session(downloader.parse_args([]), interactive=True)
        q = downloader.DownloadQueue(fake)
        n = downloader.queue_text(session, q, "https://vt.tiktok.com/a/ https://v.douyin.com/b/ "
                                              "https://qishui.douyin.com/s/c/")
        q.wait()
        self.assertEqual(n, 2)   # the Soda Music link is explained, not queued
        self.assertEqual(fake.done, ["https://vt.tiktok.com/a/", "https://v.douyin.com/b/"])

    def test_split_commands(self):
        session = downloader.Session(downloader.parse_args([]), interactive=True)
        q = downloader.DownloadQueue(FakeSession())
        for text, value in (("split on", True), ("SPLIT OFF", False), ("split auto", None)):
            self.assertTrue(downloader.handle_command(text, session, q))
            self.assertEqual(session.split, value)
        self.assertTrue(downloader.handle_command("status", session, q))
        self.assertFalse(downloader.handle_command("https://youtu.be/x", session, q))


class TestCompilationCheck(unittest.TestCase):
    @staticmethod
    def chapters(*lengths):
        out, t = [], 0
        for n in lengths:
            out.append({"start_time": t, "end_time": t + n, "title": "x"})
            t += n
        return out

    def test_hour_long_compilation_splits(self):
        ch = self.chapters(*[200] * 18)
        self.assertTrue(youtube.decide_split(ch, 3600, None))

    def test_music_video_with_section_chapters_stays_whole(self):
        ch = self.chapters(15, 45, 40, 50, 30, 40)   # intro/verse/chorus... ~3.7 min
        self.assertFalse(youtube.decide_split(ch, 220, None))

    def test_long_video_with_tiny_chapters_stays_whole(self):
        ch = self.chapters(*[30] * 30)   # 15 min of 30-second segments
        self.assertFalse(youtube.decide_split(ch, 900, None))

    def test_override_wins(self):
        self.assertTrue(youtube.decide_split(self.chapters(60, 60), 120, True))
        self.assertFalse(youtube.decide_split(self.chapters(*[200] * 18), 3600, False))

    def test_no_chapters_never_splits(self):
        self.assertFalse(youtube.decide_split([], 3600, True))


class TestCommon(unittest.TestCase):
    def test_archive_shared_format(self):
        self.assertEqual(common.ARCHIVE_NAME, ".downloaded.txt")


if __name__ == "__main__":
    unittest.main()
