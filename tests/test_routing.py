"""Routing tests: one pasted text can mix YouTube, TikTok and Douyin links."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import downloader  # noqa: E402
from mp3tool import common, links  # noqa: E402


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

    def test_interactive_asks(self):
        s = self.session([], interactive=True)
        self.assertEqual((s.want_all, s.split), (None, None))

    def test_flags_win(self):
        s = self.session(["--all", "--split", "x"], interactive=False)
        self.assertEqual((s.want_all, s.split), (True, True))

    def test_default_folders_per_platform(self):
        s = self.session([], interactive=True)
        self.assertTrue(s.folder("youtube").endswith("YouTube Music"))
        self.assertTrue(s.folder("douyin").endswith("TikTok Music"))
        s = self.session(["-o", "D:/Music"], interactive=True)
        self.assertEqual(s.folder("tiktok"), "D:/Music")

    def test_soda_link_explains_instead_of_failing_oddly(self):
        s = self.session([], interactive=True)
        self.assertFalse(s.process("soda", "https://qishui.douyin.com/s/x/"))

    def test_one_crashing_link_does_not_end_session(self):
        s = self.session([], interactive=True)
        original = downloader.tiktok.download
        downloader.tiktok.download = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            ok, failed = downloader.run_text(s, "https://vt.tiktok.com/a/ https://qishui.douyin.com/s/x/")
        finally:
            downloader.tiktok.download = original
        self.assertEqual((ok, failed), (0, 2))

    def test_douyin_cookie_jar_reused_across_links(self):
        s = self.session([], interactive=True)
        self.assertIs(s.douyin_client, s.douyin_client)


class TestCommon(unittest.TestCase):
    def test_archive_shared_format(self):
        self.assertEqual(common.ARCHIVE_NAME, ".downloaded.txt")


if __name__ == "__main__":
    unittest.main()
