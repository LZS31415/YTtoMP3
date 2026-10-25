"""TikTok / Douyin offline tests (no network needed)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mp3tool import common, douyin, links, tiktok  # noqa: E402


def extract_urls(text):
    """TikTok/Douyin links only, as the old standalone tool returned them."""
    return [u for p, u in links.extract_links(text) if p in ("tiktok", "douyin")]

AWEME_ID = "7412345678901234567"


def fake_share_page(item: dict) -> str:
    router = {"loaderData": {"video_(id)/page": {"videoInfoRes": {"item_list": [item]}}}}
    return f"<html><script>window._ROUTER_DATA = {json.dumps(router, ensure_ascii=False)}</script></html>"


class TestUrlParsing(unittest.TestCase):
    def test_douyin_share_text(self):
        text = "7.43 复制打开抖音，看看【小明的作品】好听的歌 #音乐 # 翻唱 https://v.douyin.com/iABcDeF/ q@E.Ux 06/12 HVl:/"
        self.assertEqual(extract_urls(text), ["https://v.douyin.com/iABcDeF/"])

    def test_tiktok_and_dedupe(self):
        text = "https://vt.tiktok.com/ZSabc123/ and https://www.tiktok.com/@user/video/7300000000000000000 https://vt.tiktok.com/ZSabc123/"
        self.assertEqual(len(extract_urls(text)), 2)

    def test_ignores_other_sites(self):
        self.assertEqual(extract_urls("https://youtube.com/watch?v=x https://evil-tiktok.com.example/x"), [])

    def test_platform(self):
        self.assertEqual(links.platform_of("https://www.iesdouyin.com/share/video/1/"), "douyin")
        self.assertEqual(links.platform_of("https://m.tiktok.com/v/1"), "tiktok")
        self.assertIsNone(links.platform_of("https://nottiktok.com/x"))

    def test_douyin_id_from_url(self):
        for url in (f"https://www.douyin.com/video/{AWEME_ID}",
                    f"https://www.douyin.com/jingxuan?modal_id={AWEME_ID}",
                    f"https://www.iesdouyin.com/share/video/{AWEME_ID}/?region=CN"):
            self.assertEqual(douyin.douyin_id(url), AWEME_ID)


class TestTitles(unittest.TestCase):
    def test_hashtags_removed(self):
        self.assertEqual(common.clean_title("晴天 cover #周杰伦 #翻唱 @someone", "x"), "晴天 cover")

    def test_fallback_when_only_hashtags(self):
        self.assertEqual(common.clean_title("#fyp #viral", "123"), "123")

    def test_truncation(self):
        self.assertTrue(len(common.clean_title("a" * 500, "x")) <= common.MAX_TITLE_CHARS + 1)

    def test_sanitize(self):
        self.assertEqual(common.sanitize_filename('a:b/c?"d'), "a_b_c__d")


# Trimmed copy of a real share page item (captured Oct 2026), so the parser is
# tested against what Douyin actually serves, not only a hand-made mock.
REAL_ITEM = {
    "aweme_id": "7573246156446254522",
    "desc": "如果这就是爱情 本来就不公平。 #张靓颖 #如果这就是爱情",
    "author": {"nickname": "白山茶live"},
    "music": {"author": "白山茶live", "title": "@白山茶live创作的原声"},
    "statistics": {"aweme_id": "7573246156446254522"},
    "video": {
        "cover": {"url_list": ["https://p11-sign.douyinpic.com/tos-cn-i-0813c000-ce/x~tplv-dy-resize:540:q75.webp"]},
        "play_addr": {"uri": "v1e00fgi0000d4cp69vog65m5569hpmg", "url_list": [
            "https://aweme.snssdk.com/aweme/v1/playwm/?line=0&logo_name=aweme_diversion_search&ratio=720p&video_id=v1e00fgi0000d4cp69vog65m5569hpmg"]},
    },
}
REAL_ROUTER = {"loaderData": {"video_layout": None, "video_(id)/page": {"videoInfoRes": {"item_list": [REAL_ITEM]}}}, "errors": None}
# What Douyin serves when the request has no visitor cookie: same shell, no videoInfoRes.
NO_DATA_ROUTER = {"loaderData": {"video_layout": None, "video_(id)/page": {"ua": "x", "isSpider": False, "renderInSSR": 1}}, "errors": None}


def page(router):
    return f"<html><script>window._ROUTER_DATA = {json.dumps(router, ensure_ascii=False)}</script></html>"


class TestDouyinParser(unittest.TestCase):
    def test_real_share_page(self):
        info = douyin.parse_douyin_share_page(page(REAL_ROUTER), "7573246156446254522")
        self.assertEqual(info["title"], "如果这就是爱情 本来就不公平。")
        self.assertEqual(info["artist"], "白山茶live")
        self.assertIn("/aweme/v1/play/?", info["media_url"])
        self.assertTrue(info["cover_url"].startswith("https://p11-sign.douyinpic.com/"))

    def test_cookieless_page_is_no_data(self):
        with self.assertRaises(douyin.NoPostData):
            douyin.parse_douyin_share_page(page(NO_DATA_ROUTER), "7573246156446254522")

    def test_video_post(self):
        html = fake_share_page({
            "aweme_id": AWEME_ID,
            "desc": "超好听 #music",
            "author": {"nickname": "小明"},
            "video": {"play_addr": {"url_list": ["https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0"]},
                      "cover": {"url_list": ["https://p3.douyinpic.com/cover.jpeg"]}},
            "music": {"play_url": {"url_list": ["https://sf.douyinstatic.com/music.mp3"]}},
        })
        info = douyin.parse_douyin_share_page(html, AWEME_ID)
        self.assertEqual(info["title"], "超好听")
        self.assertEqual(info["artist"], "小明")
        self.assertIn("/play/", info["media_url"])
        self.assertNotIn("playwm", info["media_url"])
        self.assertTrue(info["cover_url"].endswith("cover.jpeg"))

    def test_image_post_falls_back_to_music(self):
        html = fake_share_page({"aweme_id": AWEME_ID, "desc": "", "author": {},
                                "music": {"play_url": {"url_list": ["https://x/m.mp3"]}}})
        info = douyin.parse_douyin_share_page(html, AWEME_ID)
        self.assertEqual(info["media_url"], "https://x/m.mp3")
        self.assertEqual(info["title"], AWEME_ID)

    def test_unknown_layout(self):
        with self.assertRaises(douyin.NoPostData):
            douyin.parse_douyin_share_page("<html>blocked</html>", AWEME_ID)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TestConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.video = os.path.join(self.tmp, "in.mp4")
        self.cover = os.path.join(self.tmp, "cover.webp")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-c:v", "libx264", "-c:a", "aac", "-shortest", self.video], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=c=red:size=200x200", "-frames:v", "1", self.cover], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def probe(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_mp3_with_cover_and_tags(self):
        dest = os.path.join(self.tmp, "小明 - 晴天.mp3")
        common.convert_to_mp3(self.video, dest, "晴天", "小明", "192", self.cover, "https://v.douyin.com/x/")
        info = self.probe(dest)
        codecs = [s["codec_name"] for s in info["streams"]]
        self.assertIn("mp3", codecs)
        self.assertIn("mjpeg", codecs)  # embedded cover art
        tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
        self.assertEqual(tags["title"], "晴天")
        self.assertEqual(tags["artist"], "小明")

    def test_broken_cover_does_not_lose_song(self):
        bad = os.path.join(self.tmp, "bad.jpg")
        with open(bad, "wb") as f:
            f.write(b"not an image")
        dest = os.path.join(self.tmp, "out.mp3")
        common.convert_to_mp3(self.video, dest, "t", "a", "128", bad)
        self.assertEqual([s["codec_name"] for s in self.probe(dest)["streams"]], ["mp3"])

    def test_ytdlp_pipeline_on_local_file(self):
        """Runs the same yt-dlp options the TikTok path uses, against a local file."""
        out = os.path.join(self.tmp, "out")
        os.makedirs(out)
        opts = tiktok.build_options(out, "192", common.Stats())
        opts["enable_file_urls"] = True
        opts["progress_hooks"] = []
        import yt_dlp
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.add_post_processor(tiktok.CleanTitlePP(), when="pre_process")
            rc = ydl.download(["file://" + self.video])
        self.assertEqual(rc, 0)
        mp3s = [f for f in os.listdir(out) if f.endswith(".mp3")]
        self.assertEqual(len(mp3s), 1, os.listdir(out))


class FakeClient(douyin.DouyinClient):
    """Serves the cookie-less page until a given strategy has run."""

    def __init__(self, unlock_with, browser=None):
        super().__init__(browser)
        self.unlock_with = unlock_with
        self.unlocked = False
        self.fetches = 0

    def fetch_text(self, url):
        self.fetches += 1
        return page(REAL_ROUTER if self.unlocked else NO_DATA_ROUTER)

    def _register_ttwid(self):
        if self.unlock_with == "ttwid":
            self.unlocked = True
        elif self.unlock_with == "ttwid-error":
            raise RuntimeError("network blocked")

    def _browser_cookies(self, browser):
        if self.unlock_with == browser:
            self.unlocked = True
        else:
            raise RuntimeError("no cookies")


class TestDouyinEscalation(unittest.TestCase):
    ID = "7573246156446254522"

    def test_ttwid_unlocks(self):
        c = FakeClient("ttwid")
        self.assertEqual(c.fetch_info(self.ID)["artist"], "白山茶live")

    def test_falls_through_to_browser(self):
        c = FakeClient("firefox")
        self.assertEqual(c.fetch_info(self.ID)["artist"], "白山茶live")

    def test_explicit_browser_only(self):
        c = FakeClient("edge", browser="edge")
        self.assertEqual(c.browsers, ("edge",))
        self.assertEqual(c.fetch_info(self.ID)["artist"], "白山茶live")

    def test_gives_up_with_page_attached(self):
        c = FakeClient("nothing")
        with self.assertRaises(douyin.NoPostData) as ctx:
            c.fetch_info(self.ID)
        self.assertTrue(ctx.exception.html.startswith("<html>"))

    def test_strategies_not_repeated_for_next_link(self):
        c = FakeClient("ttwid")
        c.fetch_info(self.ID)
        before = c.fetches
        c.fetch_info(self.ID)  # cookie already in jar -> one fetch, no escalation
        self.assertEqual(c.fetches - before, 1)


class TestArchive(unittest.TestCase):
    def test_roundtrip(self):
        tmp = tempfile.mkdtemp()
        try:
            self.assertFalse(common.in_archive(tmp, "douyin 1"))
            common.add_to_archive(tmp, "douyin 1")
            self.assertTrue(common.in_archive(tmp, "douyin 1"))
            self.assertFalse(common.in_archive(tmp, "douyin 11"))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
