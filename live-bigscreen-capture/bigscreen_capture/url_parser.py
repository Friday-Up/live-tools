from urllib.parse import parse_qs, urlparse

from .models import ParsedBigscreenUrl


class BigscreenUrlError(ValueError):
    pass


def parse_bigscreen_url(raw_url):
    raw_url = (raw_url or "").strip()
    if not raw_url:
        raise BigscreenUrlError("请填写蓝屏页面链接")

    parsed = urlparse(raw_url)
    if parsed.netloc != "jlive.jd.com":
        raise BigscreenUrlError("链接必须是 jlive.jd.com 的蓝屏页面")
    if "/bigScreen" not in parsed.path:
        raise BigscreenUrlError("链接必须是蓝屏 bigScreen 页面")

    room_ids = parse_qs(parsed.query).get("id") or []
    room_id = room_ids[0].strip() if room_ids else ""
    if not room_id:
        raise BigscreenUrlError("链接中没有识别到直播间 ID")

    return ParsedBigscreenUrl(url=raw_url, room_id=room_id)
