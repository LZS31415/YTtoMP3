"""Find links in whatever the user pasted and work out which site they are."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# Stops at whitespace and the full-width punctuation Douyin's share text uses.
URL_RE = re.compile(r"https?://[^\s<>\"'，。！？、；）】]+", re.IGNORECASE)

# Soda Music (汽水音乐) lives on douyin.com subdomains, so it must be checked
# before Douyin or its links would be misread as Douyin videos.
SODA_HOSTS = ("qishui.douyin.com", "music.douyin.com")
YOUTUBE_HOSTS = ("youtube.com", "youtu.be")
TIKTOK_HOSTS = ("tiktok.com",)
DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _matches(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def platform_of(url: str) -> str | None:
    """'youtube', 'tiktok', 'douyin', 'soda' or None."""
    host = host_of(url)
    if _matches(host, SODA_HOSTS):
        return "soda"
    if _matches(host, YOUTUBE_HOSTS):
        return "youtube"
    if _matches(host, TIKTOK_HOSTS):
        return "tiktok"
    if _matches(host, DOUYIN_HOSTS):
        return "douyin"
    return None


def extract_links(text: str) -> list[tuple[str, str]]:
    """Every supported link in the pasted text, as (platform, url), in order.

    The TikTok/Douyin share button copies a blob like
    '7.43 复制打开抖音，看看【某某的作品】... https://v.douyin.com/AbCdEf/ q@E.Ux 06/12'
    so the input can't be assumed to be a clean URL.
    """
    found: list[tuple[str, str]] = []
    for raw in URL_RE.findall(text):
        url = raw.rstrip(".,;:!?)]}")
        platform = platform_of(url)
        if platform and (platform, url) not in found:
            found.append((platform, url))
    return found


# --------------------------------------------------------------------------- #
# YouTube link shapes
# --------------------------------------------------------------------------- #

def youtube_kind(url: str) -> str:
    """'video', 'playlist', 'video_in_playlist' or 'video_in_mix'."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    list_id = (query.get("list") or [""])[0]
    has_video = bool(query.get("v")) or parsed.hostname == "youtu.be" or "/shorts/" in parsed.path
    if not list_id:
        return "video"
    if not has_video:
        return "playlist"
    # RD... lists are auto-generated Mixes / radio: long, and never what you
    # meant if you just copied the link of the song you were listening to.
    return "video_in_mix" if list_id.startswith("RD") else "video_in_playlist"


def single_video_url(url: str) -> str:
    """Strip playlist parameters so only the song itself is downloaded."""
    parsed = urlparse(url)
    if parsed.hostname == "youtu.be":
        return f"https://youtu.be{parsed.path}"
    video_id = parse_qs(parsed.query).get("v", [""])[0]
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else url
