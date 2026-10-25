"""Douyin: video and image posts via the mobile share page.

yt-dlp's Douyin support needs fresh browser cookies and doesn't understand the
v.douyin.com links people copy from the app, so Douyin has its own resolver.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import shutil
import tempfile
import urllib.request

from .common import (add_to_archive, clean_title, convert_to_mp3, in_archive,
                     sanitize_filename, say, unique_path)

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
DOUYIN_ID_RE = re.compile(r"(?:/(?:video|note|slides)/|[?&]modal_id=)(\d{15,})")


class NoPostData(RuntimeError):
    """The share page loaded, but Douyin left the post data out of it."""


TTWID_REGISTER_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
TTWID_REGISTER_BODY = {
    "region": "cn", "aid": 1768, "needFid": False, "service": "www.ixigua.com",
    "migrate_info": {"ticket": "", "source": "node"}, "cbUrlProtocol": "https", "union": True,
}
AUTO_BROWSERS = ("firefox", "edge", "chrome")


class DouyinClient:
    """Fetches Douyin share pages with a cookie jar that lives for the whole run.

    Douyin only includes the post data in the share page when the request
    carries a session cookie that a normal browser would already have. A bare
    request gets the page shell with the data stripped out. So the client
    escalates until the data shows up:
      1. plain visit (keeps any cookies Douyin sets), then a second visit
      2. register an anonymous 'ttwid' visitor token, as Douyin's web app does
      3. borrow Douyin cookies from a browser on this PC (Firefox is the most
         reliable on Windows; Chrome/Edge encrypt cookies in a way that often
         cannot be read)
    Whatever works is kept in the jar, so later links in the same run are fast.
    """

    def __init__(self, browser: str | None = None):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.browsers = (browser,) if browser else AUTO_BROWSERS
        self.used: set[str] = set()

    # -- HTTP --------------------------------------------------------------- #
    def open(self, url: str, referer: str | None = None, timeout: int = 20,
             data: bytes | None = None, headers: dict | None = None):
        h = {"User-Agent": MOBILE_UA, "Accept-Language": "zh-CN,zh;q=0.9",
             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        if referer:
            h["Referer"] = referer
        h.update(headers or {})
        return self.opener.open(urllib.request.Request(url, data=data, headers=h), timeout=timeout)

    def fetch_text(self, url: str) -> str:
        with self.open(url) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def download(self, url: str, dest: str) -> None:
        with self.open(url, referer="https://www.douyin.com/", timeout=60) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)

    # -- cookie strategies --------------------------------------------------- #
    def _set_cookie(self, name: str, value: str, domain: str) -> None:
        self.jar.set_cookie(http.cookiejar.Cookie(
            0, name, value, None, False, domain, True, domain.startswith("."), "/", True,
            True, None, False, None, None, {}))

    def _register_ttwid(self) -> None:
        body = json.dumps(TTWID_REGISTER_BODY).encode()
        with self.open(TTWID_REGISTER_URL, data=body, headers={"Content-Type": "application/json"}) as r:
            r.read()
        ttwid = next((c.value for c in self.jar if c.name == "ttwid"), None)
        if not ttwid:
            raise RuntimeError("no token returned")
        for domain in (".iesdouyin.com", ".douyin.com"):
            self._set_cookie("ttwid", ttwid, domain)

    def _browser_cookies(self, browser: str) -> None:
        from yt_dlp.cookies import extract_cookies_from_browser
        browser_jar = extract_cookies_from_browser(browser, logger=_SilentLogger())
        n = 0
        for c in browser_jar:
            if "douyin" in c.domain:
                self.jar.set_cookie(c)
                n += 1
        if not n:
            raise RuntimeError(f"no Douyin cookies found (open douyin.com in {browser} once)")

    def _strategies(self):
        yield "a second visit", None
        yield "an anonymous visitor token", self._register_ttwid
        for b in self.browsers:
            yield f"{b.capitalize()} cookies", lambda b=b: self._browser_cookies(b)

    # -- main entry ---------------------------------------------------------- #
    def fetch_info(self, aweme_id: str) -> dict:
        share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
        html = self.fetch_text(share_url)
        try:
            return parse_douyin_share_page(html, aweme_id)
        except NoPostData:
            pass

        for label, prepare in self._strategies():
            if label in self.used:
                continue
            self.used.add(label)
            if prepare:
                try:
                    prepare()
                except Exception as e:
                    say(f"    ({label} unavailable: {str(e)[:120]})")
                    continue
            html = self.fetch_text(share_url)
            try:
                info = parse_douyin_share_page(html, aweme_id)
            except NoPostData:
                continue
            say(f"  Got the post using {label}.")
            return info

        err = NoPostData(
            "Douyin withheld the post data even with cookies. Open douyin.com once in Firefox, "
            "then run again with --browser firefox."
        )
        err.html = html
        raise err


class _SilentLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass

    def progress_bar(self):
        return None


def douyin_id(url: str, client: "DouyinClient | None" = None) -> str:
    """Get the numeric video id, following v.douyin.com short links if needed."""
    m = DOUYIN_ID_RE.search(url)
    if m:
        return m.group(1)
    client = client or DouyinClient()
    with client.open(url) as resp:  # short link -> redirects to /share/video/<id>/
        final = resp.geturl()
    m = DOUYIN_ID_RE.search(final)
    if not m:
        raise RuntimeError(f"Could not find a video id in {final}")
    return m.group(1)


def _find_aweme(node, aweme_id: str):
    """Search the page JSON for the post object. Layout changes often, so we
    look for the shape (has 'aweme_id' and 'video' or 'music') instead of a
    fixed path."""
    if isinstance(node, dict):
        if str(node.get("aweme_id")) == aweme_id and ("video" in node or "music" in node):
            return node
        for v in node.values():
            found = _find_aweme(v, aweme_id)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_aweme(v, aweme_id)
            if found:
                return found
    return None


def _first_url(obj) -> str | None:
    urls = (obj or {}).get("url_list") or []
    return urls[0] if urls else None


def parse_douyin_share_page(html: str, aweme_id: str) -> dict:
    m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", html, re.DOTALL)
    if not m:
        raise NoPostData("Douyin returned a page without post data (verification page?).")
    item = _find_aweme(json.loads(m.group(1)), aweme_id)
    if not item:
        raise NoPostData("Share page has no post data (cookies needed, or post deleted/private).")

    video = item.get("video") or {}
    music = item.get("music") or {}
    video_url = _first_url(video.get("play_addr"))
    if video_url:
        video_url = video_url.replace("/playwm/", "/play/")  # no-watermark variant
    music_url = _first_url(music.get("play_url"))
    media_url = video_url or music_url  # image posts (图文) only have background music
    if not media_url:
        raise RuntimeError("No playable media found for this post.")

    return {
        "id": aweme_id,
        "title": clean_title(item.get("desc"), aweme_id),
        "artist": (item.get("author") or {}).get("nickname") or "Unknown",
        "media_url": media_url,
        "cover_url": _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
        or _first_url(music.get("cover_large")),
    }


def save_debug_page(out_dir: str, aweme_id: str, html: str) -> str:
    path = os.path.join(out_dir, "_debug", f"douyin_{aweme_id}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def download(url: str, out_dir: str, quality: str, client: DouyinClient) -> bool:
    os.makedirs(out_dir, exist_ok=True)
    try:
        aweme_id = douyin_id(url, client)
        key = f"douyin {aweme_id}"
        if in_archive(out_dir, key):
            say("  Nothing new: already in the folder.")
            return True

        info = client.fetch_info(aweme_id)
        say(f"  Downloading: {info['artist']} - {info['title']}")
        dest = unique_path(
            os.path.join(out_dir, sanitize_filename(f"{info['artist']} - {info['title']}") + ".mp3"),
            info["id"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media")
            client.download(info["media_url"], media)
            cover = None
            if info["cover_url"]:
                try:
                    cover = os.path.join(tmp, "cover")
                    client.download(info["cover_url"], cover)
                except Exception:
                    cover = None
            say("  Converting to MP3...")
            convert_to_mp3(media, dest, info["title"], info["artist"], quality, cover, url)

        add_to_archive(out_dir, key)
        say(f"  Saved: {os.path.basename(dest)}")
        return True
    except Exception as e:
        say(f"  Failed: {e}")
        html = getattr(e, "html", None)
        if html:
            try:
                path = save_debug_page(out_dir, douyin_id(url), html)
                say(f"  Saved what Douyin returned to {path} (send this file if you need help).")
            except Exception:
                pass
        return False
