"""Offline tests (no YouTube access needed). Run:  python -m unittest discover tests"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import downloader as d  # noqa: E402
import yt_dlp  # noqa: E402


class TestLinks(unittest.TestCase):
    def test_classify(self):
        cases = {
            "https://www.youtube.com/watch?v=8Sy0AUxIbgw&list=RD8Sy0AUxIbgw&start_radio=1": "video_in_mix",
            "https://www.youtube.com/watch?v=abc&list=PLxyz&index=3": "video_in_playlist",
            "https://www.youtube.com/playlist?list=PLxyz": "playlist",
            "https://youtu.be/abc?si=123": "video",
            "https://youtu.be/abc?list=PLxyz": "video_in_playlist",
            "https://music.youtube.com/watch?v=abc": "video",
            "https://www.youtube.com/shorts/abc": "video",
        }
        for url, kind in cases.items():
            self.assertEqual(d.classify(url), kind, url)

    def test_single_video_url_strips_list(self):
        self.assertEqual(
            d.single_video_url("https://www.youtube.com/watch?v=8Sy0AUxIbgw&list=RD8Sy0AUxIbgw&start_radio=1"),
            "https://www.youtube.com/watch?v=8Sy0AUxIbgw")
        self.assertEqual(d.single_video_url("https://youtu.be/abc?list=PLx"), "https://youtu.be/abc")

    def test_is_youtube(self):
        self.assertTrue(d.is_youtube("https://m.youtube.com/watch?v=1"))
        self.assertFalse(d.is_youtube("https://notyoutube.com/watch?v=1"))

    def test_choice_without_prompt(self):
        mix = "https://www.youtube.com/watch?v=abc&list=RDabc"
        self.assertEqual(d.resolve_choice(mix, "video_in_mix", False), ("https://www.youtube.com/watch?v=abc", False))
        self.assertEqual(d.resolve_choice(mix, "video_in_mix", True), (mix, True))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TestPipeline(unittest.TestCase):
    """Runs the real yt-dlp + ffmpeg pipeline on a local 3-chapter file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src.webm")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=9", "-c:a", "libopus", self.src], check=True)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_info(self, chapters=True):
        info = {
            "id": "abc123", "title": "Top Hits Compilation", "uploader": "Some Channel",
            "url": "file://" + self.src, "ext": "webm", "extractor": "generic",
            "extractor_key": "Generic", "webpage_url": "https://www.youtube.com/watch?v=abc123",
        }
        if chapters:
            info["chapters"] = [
                {"start_time": 0, "end_time": 3, "title": "Song One"},
                {"start_time": 3, "end_time": 6, "title": "Song Two"},
                {"start_time": 6, "end_time": 9, "title": "Song Three"},
            ]
        return info

    def run_pipeline(self, info, split):
        stats = d.Stats()
        opts = d.build_options(self.out, "128", False, stats)
        opts["enable_file_urls"] = True
        opts["progress_hooks"] = []
        with yt_dlp.YoutubeDL(opts) as ydl:
            if split:
                ydl.add_post_processor(d.SplitIntoSongsPP(ydl, stats), when="post_process")
            ydl.process_ie_result(info, download=True)
        return stats

    def test_split_into_tagged_songs(self):
        stats = self.run_pipeline(self.fake_info(), split=True)
        folder = os.path.join(self.out, "Top Hits Compilation")
        self.assertEqual(sorted(os.listdir(folder)),
                         ["01 - Song One.mp3", "02 - Song Two.mp3", "03 - Song Three.mp3"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "Top Hits Compilation.mp3")))  # long file removed
        self.assertEqual(stats.songs, 3)
        from mutagen.easyid3 import EasyID3
        tags = EasyID3(os.path.join(folder, "02 - Song Two.mp3"))
        self.assertEqual(tags["title"], ["Song Two"])
        self.assertEqual(tags["album"], ["Top Hits Compilation"])
        self.assertEqual(tags["tracknumber"], ["2/3"])

    def test_no_split_keeps_one_file(self):
        stats = self.run_pipeline(self.fake_info(), split=False)
        self.assertEqual([f for f in os.listdir(self.out) if f.endswith(".mp3")], ["Top Hits Compilation.mp3"])
        self.assertEqual((stats.done, stats.songs), (1, 0))

    def test_split_requested_but_no_chapters_keeps_file(self):
        stats = self.run_pipeline(self.fake_info(chapters=False), split=True)
        self.assertIn("Top Hits Compilation.mp3", os.listdir(self.out))
        self.assertEqual(stats.songs, 0)

    def test_already_downloaded_is_skipped(self):
        self.run_pipeline(self.fake_info(), split=False)
        archive = open(os.path.join(self.out, d.ARCHIVE_NAME)).read()
        self.assertIn("abc123", archive)


if __name__ == "__main__":
    unittest.main()
