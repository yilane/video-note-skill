"""抖音公开视频下载。

用于 video-note skill 的轻量独立实现:
- 不依赖 BiliNote 后端配置/数据库
- 默认免登录,可用 DOUYIN_COOKIE 或 cookie 参数兜底
- 音频下载后交给现有 bcut/kuaishou ASR
"""
import datetime
import os
import re
import tempfile
from typing import Optional
from urllib.parse import quote, urlencode

import requests


DOUYIN_DOMAIN = "https://www.douyin.com"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


BASE_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": 1,
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": 1920,
    "screen_height": 1080,
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "130.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "130.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": 12,
    "device_memory": 8,
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "from_user_page": "1",
    "locate_query": "false",
    "need_time_list": "1",
    "pc_libra_divert": "Windows",
    "publish_video_strategy_type": "2",
    "round_trip_time": "0",
    "show_live_replay_strategy": "1",
    "time_list_query": "0",
    "whale_cut_token": "",
    "update_version_code": "170400",
}


def extract_aweme_id(text: str, proxy: Optional[str] = None) -> Optional[str]:
    """从抖音 URL 或分享文案中提取 aweme_id。"""
    if not text:
        return None

    url = _first_url(text) or text
    resolved = _resolve_url(url, proxy=proxy)
    candidates = [resolved, url, text]
    patterns = [r"/video/(\d+)", r"[?&]aweme_id=(\d+)"]
    for candidate in candidates:
        for pattern in patterns:
            match = re.search(pattern, candidate)
            if match:
                return match.group(1)
    return None


def fetch_video_info(
    video_url: str,
    cookie: Optional[str] = None,
    proxy: Optional[str] = None,
    use_browser_cookie: bool = True,
    browser_cookie: Optional[str] = "auto",
) -> dict:
    """请求抖音 aweme/detail,返回 aweme_detail。失败抛 RuntimeError。"""
    aweme_id = extract_aweme_id(video_url, proxy=proxy)
    if not aweme_id:
        raise RuntimeError("无法从抖音链接中解析视频 ID")

    params = dict(BASE_PARAMS)
    params["aweme_id"] = aweme_id
    params["msToken"] = _gen_ms_token(proxy=proxy)
    a_bogus = quote(_gen_a_bogus(params), safe="")
    detail_url = f"{DOUYIN_DOMAIN}/aweme/v1/web/aweme/detail/?{urlencode(params)}&a_bogus={a_bogus}"

    effective_cookie = cookie or os.environ.get("DOUYIN_COOKIE")
    resp = _request_detail(detail_url, effective_cookie, proxy)
    resp.raise_for_status()
    if _needs_fresh_cookie(resp) and not effective_cookie and use_browser_cookie:
        effective_cookie = load_browser_cookie(browser_cookie)
        if effective_cookie:
            resp = _request_detail(detail_url, effective_cookie, proxy)
            resp.raise_for_status()
    if not resp.content:
        raise RuntimeError(_fresh_cookie_message())
    try:
        data = resp.json()
    except ValueError as e:
        raise RuntimeError(_fresh_cookie_message("抖音接口没有返回有效 JSON")) from e
    detail = data.get("aweme_detail")
    if not detail:
        msg = data.get("status_msg") or data.get("message") or "抖音接口未返回视频详情"
        raise RuntimeError(msg)
    return detail


def download_audio(
    video_url: str,
    output_dir: Optional[str] = None,
    cookie: Optional[str] = None,
    proxy: Optional[str] = None,
    use_browser_cookie: bool = True,
    browser_cookie: Optional[str] = "auto",
    output_name: Optional[str] = None,
) -> dict:
    """下载抖音音频,返回 {audio_path, video_id, title, duration}。

    output_name 指定时,文件名用 ``<output_name>.mp3``(不含扩展名);
    否则回退 ``<aweme_id>.mp3``。调用方应自行清洗 output_name。
    """
    output_dir = output_dir or tempfile.mkdtemp(prefix="video_note_douyin_")
    os.makedirs(output_dir, exist_ok=True)

    detail = fetch_video_info(
        video_url,
        cookie=cookie,
        proxy=proxy,
        use_browser_cookie=use_browser_cookie,
        browser_cookie=browser_cookie,
    )
    video_id = detail["aweme_id"]
    audio_url = _first_media_url(detail.get("music", {}).get("play_url", {}))
    if not audio_url:
        raise RuntimeError("抖音详情中没有可用音频地址")

    file_stem = output_name or video_id
    output_path = os.path.join(output_dir, f"{file_stem}.mp3")
    _download_file(audio_url, output_path, cookie=cookie, proxy=proxy)
    return {
        "audio_path": output_path,
        "video_id": video_id,
        "title": detail.get("item_title") or detail.get("desc") or video_id,
        "duration": float(detail.get("video", {}).get("duration") or 0) / 1000.0,
    }


def download_video(
    video_url: str,
    output_dir: Optional[str] = None,
    cookie: Optional[str] = None,
    proxy: Optional[str] = None,
    use_browser_cookie: bool = True,
    browser_cookie: Optional[str] = "auto",
    output_name: Optional[str] = None,
) -> str:
    """下载抖音视频(mp4),返回本地路径。

    output_name 指定时,文件名用 ``<output_name>.mp4``(不含扩展名);
    否则回退 ``<aweme_id>.mp4``。已存在同名文件时跳过下载直接返回。
    """
    output_dir = output_dir or tempfile.mkdtemp(prefix="video_note_douyin_")
    os.makedirs(output_dir, exist_ok=True)

    detail = fetch_video_info(
        video_url,
        cookie=cookie,
        proxy=proxy,
        use_browser_cookie=use_browser_cookie,
        browser_cookie=browser_cookie,
    )
    video_id = detail["aweme_id"]
    file_stem = output_name or video_id
    output_path = os.path.join(output_dir, f"{file_stem}.mp4")
    if os.path.exists(output_path):
        return output_path

    media_url = select_video_url(detail)
    if not media_url:
        raise RuntimeError("抖音详情中没有可用视频地址")

    _download_file(media_url, output_path, cookie=cookie, proxy=proxy)
    return output_path


def select_video_url(detail: dict) -> Optional[str]:
    """优先选择 bit_rate.play_addr 中的 mp4 地址,通常无抖音品牌 Logo。"""
    bit_rate_list = []
    for item in detail.get("video", {}).get("bit_rate", []) or []:
        if item.get("format") != "mp4":
            continue
        play_addr = item.get("play_addr") or {}
        url = _first_media_url(play_addr)
        if not url:
            continue
        resolution = _resolution_number(item.get("gear_name", ""), play_addr)
        bit_rate_list.append({
            "url": url,
            "resolution": resolution,
            "bit_rate": int(item.get("bit_rate") or 0),
            "data_size": int(play_addr.get("data_size") or 0),
        })

    if bit_rate_list:
        bit_rate_list.sort(
            key=lambda item: (item["resolution"], item["bit_rate"], item["data_size"]),
            reverse=True,
        )
        return bit_rate_list[0]["url"]

    video = detail.get("video", {})
    media_url = _first_media_url(video.get("play_addr", {}))
    if media_url:
        return media_url
    return _first_media_url(video.get("download_addr", {}))


def _first_url(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0) if match else None


def _resolve_url(url: str, proxy: Optional[str] = None) -> str:
    try:
        resp = requests.head(
            url,
            headers=_headers(None),
            allow_redirects=True,
            proxies=_proxies(proxy),
            timeout=15,
        )
        return resp.url
    except requests.RequestException:
        return url


def _gen_ms_token(proxy: Optional[str] = None) -> str:
    payload = {
        "magic": 538969122,
        "version": 1,
        "dataType": 8,
        "strData": _MS_TOKEN_STR_DATA,
        "tspFromClient": _timestamp_ms(),
    }
    resp = requests.post(
        "https://mssdk.bytedance.com/web/report",
        json=payload,
        headers={"User-Agent": DEFAULT_UA, "Content-Type": "application/json"},
        proxies=_proxies(proxy),
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.cookies.get("msToken")
    if not token:
        raise RuntimeError("未能获取抖音 msToken")
    return token


def _gen_a_bogus(params: dict) -> str:
    try:
        from sources.douyin_abogus import ABogus
    except ModuleNotFoundError as e:
        if e.name == "gmssl":
            raise RuntimeError("缺少 gmssl 依赖,请先安装 video-note/scripts/requirements.txt") from e
        raise
    return ABogus().get_value(params)


def load_browser_cookie(browser: Optional[str] = "auto") -> Optional[str]:
    """读取浏览器里的 .douyin.com cookie,不打印、不保存。"""
    try:
        import browser_cookie3
    except ModuleNotFoundError:
        return None

    loaders = _browser_cookie_loaders(browser_cookie3, browser)
    for loader in loaders:
        try:
            jar = loader(domain_name=".douyin.com")
        except Exception:
            continue
        cookie = _cookiejar_to_header(jar)
        if cookie:
            return cookie
    return None


def _request_detail(detail_url: str, cookie: Optional[str], proxy: Optional[str]) -> requests.Response:
    return requests.get(
        detail_url,
        headers=_headers(cookie),
        proxies=_proxies(proxy),
        timeout=30,
    )


def _needs_fresh_cookie(resp: requests.Response) -> bool:
    return not resp.content


def _fresh_cookie_message(prefix: str = "抖音接口返回空响应") -> str:
    return (
        f"{prefix},这个链接可能需要 fresh cookie。"
        "已尝试自动读取 Chrome/Edge 的 .douyin.com cookie;"
        "如果仍失败,请先用浏览器打开一次抖音页面,或设置 DOUYIN_COOKIE 后重试。"
    )


def _headers(cookie: Optional[str]) -> dict:
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "User-Agent": DEFAULT_UA,
        "Referer": "https://www.douyin.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _proxies(proxy: Optional[str]) -> Optional[dict]:
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _browser_cookie_loaders(browser_cookie3, browser: Optional[str]) -> list:
    browser = (browser or "auto").lower()
    mapping = {
        "chrome": [browser_cookie3.chrome],
        "edge": [browser_cookie3.edge],
        "firefox": [browser_cookie3.firefox],
        "auto": [browser_cookie3.chrome, browser_cookie3.edge],
    }
    return mapping.get(browser, mapping["auto"])


def _cookiejar_to_header(cookie_jar) -> Optional[str]:
    pairs = []
    for cookie in cookie_jar:
        if cookie.name and cookie.value:
            pairs.append(f"{cookie.name}={cookie.value}")
    return "; ".join(pairs) if pairs else None


def _first_media_url(play_info: dict) -> Optional[str]:
    urls = play_info.get("url_list") or []
    if urls:
        return sorted(urls, key=len)[0]
    uri = play_info.get("uri")
    if uri and uri.startswith("http"):
        return uri
    return None


def _resolution_number(gear_name: str, play_addr: dict) -> int:
    fallback = min(int(play_addr.get("width") or 0), int(play_addr.get("height") or 0))
    gear_name = gear_name or ""
    for marker, value in [
        ("1440", 1440),
        ("1080", 1080),
        ("720", 720),
        ("540", 540),
        ("480", 480),
        ("360", 360),
        ("4_", 2160),
    ]:
        if marker in gear_name:
            return value
    match = re.search(r"(\d{3,4})_", gear_name) or re.search(r"(\d{3,4})", gear_name)
    if match:
        return int(match.group(1))
    return fallback


def _download_file(url: str, output_path: str, cookie: Optional[str], proxy: Optional[str]) -> None:
    resp = requests.get(
        url,
        headers=_headers(cookie),
        proxies=_proxies(proxy),
        allow_redirects=True,
        timeout=120,
    )
    resp.raise_for_status()
    if not resp.content:
        raise RuntimeError("下载内容为空")
    with open(output_path, "wb") as f:
        f.write(resp.content)


def _timestamp_ms() -> int:
    now = datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)
    return int(now.total_seconds() * 1000)


_MS_TOKEN_STR_DATA = (
    "fWOdJTQR3/jwmZqBBsPO6tdNEc1jX7YTwPg0Z8CT+j3HScLFbj2Zm1XQ7/lqgSutntVKLJWaY3Hc/+vc0h+So9N1t6EqiImu5jKyUa+S4NPy6cNP0x9CUQQgb4+RRihCgsn4QyV8jivEFOsj3N5zFQbzXRyOV+9aG5B5EAnwpn8C70llsWq0zJz1VjN6y2KZiBZRyonAHE8feSGpwMDeUTllvq6BG3AQZz7RrORLWNCLEoGzM6bMovYVPRAJipuUML4Hq/568bNb5vqAo0eOFpvTZjQFgbB7f/CtAYYmnOYlvfrHKBKvb0TX6AjYrw2qmNNEer2ADJosmT5kZeBsogDui8rNiI/OOdX9PVotmcSmHOLRfw1cYXTgwHXr6cJeJveuipgwtUj2FNT4YCdZfUGGyRDz5bR5bdBuYiSRteSX12EktobsKPksdhUPGGv99SI1QRVmR0ETdWqnKWOj/7ujFZsNnfCLxNfqxQYEZEp9/U01CHhWLVrdzlrJ1v+KJH9EA4P1Wo5/2fuBFVdIz2upFqEQ11DJu8LSyD43qpTok+hFG3Moqrr81uPYiyPHnUvTFgwA/TIE11mTc/pNvYIb8IdbE4UAlsR90eYvPkI+rK9KpYN/l0s9ti9sqTth12VAw8tzCQvhKtxevJRQntU3STeZ3coz9Dg8qkvaSNFWuBDuyefZBGVSgILFdMy33//l/eTXhQpFrVc9OyxDNsG6cvdFwu7trkAENHU5eQEWkFSXBx9Ml54+fa3LvJBoacfPViyvzkJworlHcYYTG392L4q6wuMSSpYUconb+0c5mwqnnLP6MvRdm/bBTaY2Q6RfJcCxyLW0xsJMO6fgLUEjAg/dcqGxl6gDjUVRWbCcG1NAwPCfmYARTuXQYbFc8LO+r6WQTWikO9Q7Cgda78pwH07F8bgJ8zFBbWmyrghilNXENNQkyIzBqOQ1V3w0WXF9+Z3vG3aBKCjIENqAQM9qnC14WMrQkfCHosGbQyEH0n/5R2AaVTE/ye2oPQBWG1m0Gfcgs/96f6yYrsxbDcSnMvsA+okyd6GfWsdZYTIK1E97PYHlncFeOjxySjPpfy6wJc4UlArJEBZYmgveo1SZAhmXl3pJY3yJa9CmYImWkhbpwsVkSmG3g11JitJXTGLIfqKXSAhh+7jg4HTKe+5KNir8xmbBI/DF8O/+diFAlD+BQd3cV0G4mEtCiPEhOvVLKV1pE+fv7nKJh0t38wNVdbs3qHtiQNN7JhY4uWZAosMuBXSjpEtoNUndI+o0cjR8XJ8tSFnrAY8XihiRzLMfeisiZxWCvVwIP3kum9MSHXma75cdCQGFBfFRj0jPn1JildrTh2vRgwG+KeDZ33BJ2VGw9PgRkztZ2l/W5d32jc7H91FftFFhwXil6sA23mr6nNp6CcrO7rOblcm5SzXJ5MA601+WVicC/g3p6A0lAnhjsm37qP+xGT+cbCFOfjexDYEhnqz0QZm94CCSnilQ9B/HBLhWOddp9GK0SABIk5i3xAH701Xb4HCcgAulvfO5EK0RL2eN4fb+CccgZQeO1Zzo4qsMHc13UG0saMgBEH8SqYlHz2S0CVHuDY5j1MSV0nsShjM01vIynw6K0T8kmEyNjt1eRGlleJ5lvE8vonJv7rAeaVRZ06rlYaxrMT6cK3RSHd2liE50Z3ik3xezwWoaY6zBXvCzljyEmqjNFgAPU3gI+N1vi0MsFmwAwFzYqqWdk3jwRoWLp//FnawQX0g5T64CnfAe/o2e/8o5/bvz83OsAAwZoR48GZzPu7KCIN9q4GBjyrePNx5Csq2srblifmzSKwF5MP/RLYsk6mEE15jpCMKOVlHcu0zhJybNP3AKMVllF6pvn+HWvUnLXNkt0A6zsfvjAva/tbLQiiiYi6vtheasIyDz3HpODlI+BCkV6V8lkTt7m8QJ1IcgTfqjQBummyjYTSwsQji3DdNCnlKYd13ZQa545utqu837FFAzOZQhbnC3bKqeJqO2sE3m7WBUMbRWLflPRqp/PsklN+9jBPADKxKPl8g6/NZVq8fB1w68D5EJlGExdDhglo4B0aihHhb1u3+zJ2DqkxkPCGBAZ2AcuFIDzD53yS4NssoWb4HJ7YyzPaJro+tgG9TshWRBtUw8Or3m0OtQtX+rboYn3+GxvD1O8vWInrg5qxnepelRcQzmnor4rHF6ZNhAJZAf18Rjncra00HPJBugY5rD+EwnN9+mGQo43b01qBBRYEnxy9JJYuvXxNXxe47/MEPOw6qsxN+dmyIWZSuzkw8K+iBM/anE11yfU4qTFt0veCaVprK6tXaFK0ZhGXDOYJd70sjIP4UrPhatp8hqIXSJ2cwi70B+TvlDk/o19CA3bH6YxrAAVeag1P9hmNlfJ7NxK3Jp7+Ny1Vd7JHWVF+R6rSJiXXPfsXi3ZEy0klJAjI51NrDAnzNtgIQf0V8OWeEVv7F8Rsm3/GKnjdNOcDKymi9agZUgtctENWbCXGFnI40NHuVHtBRZeYAYtwfV7v6U0bP9s7uZGpkp+OETHMv3AyV0MVbZwQvarnjmct4Z3Vma+DvT+Z4VlMVnkC2x2FLt26K3SIMz+KV2XLv5ocEdPFSn1vMR7zruCWC8XqAG288biHo/soldmb/nlw8o8qlfZj4h296K3hfdFubGIUtqgsrZCrLCkkRC08Cv1ozEX/y6t2YrQepwiNmwDVk5IufStVvJMj+y2r9TcYLv7UKWXx3P6aySvM2ZHPaZhv+6Z/A/jIMBSvOizn4qG11iK7Oo6JYhxCSMJZsetjsnL4ecSIAufEmoFlAScWBh6nFArRpVLvkAZ3tej7H2lWFRXIU7x7mdBfGqU82PpM6znKMMZCpEsvHqpkSPSL+Kwz2z1f5wW7BKcKK4kNZ8iveg9VzY1NNjs91qU8DJpUnGyM04C7KNMpeilEmoOxvyelMQdi85ndOVmigVKmy5JYlODNX744sHpeqmMEK/ux3xY5O406lm7dZlyGPSMrFWbm4rzqvSEIskP43+9xVP8L84GeHE4RpOHg3qh/shx+/WnT1UhKuKpByHCpLoEo144udpzZswCYSMp58uPrlwdVF31//AacTRk8dUP3tBlnSQPa1eTpXWFCn7vIiqOTXaRL//YQK+e7ssrgSUnwhuGKJ8aqNDgdsL+haVZnV9g5Qrju643adyNixvYFEp0uxzOzVkekOMh2FYnFVIL2mJYGpZEXlAIC0zQbb54rSP89j0G7soJ2HcOkD0NmMEWj/7hUdTuMin1lRNde/qmHjwhbhqL8Z9MEO/YG3iLMgFTgSNQQhyE8AZAAKnehmzjORJfbK+qxyiJ07J843EDduzOoYt9p/YLqyTFmAgpdfK0uYrtAJ47cbl5WWhVXp5/XUxwWdL7TvQB0Xh6ir1/XBRcsVSDrR7cPE221ThmW1EPzD+SPf2L2gS0WromZqj1PhLgk92YnnR9s7/nLBXZHPKy+fDbJT16QqabFKqAl9G0blyf+R5UGX2kN+iQp4VGXEoH5lXxNNTlgRskzrW7KliQXcac20oimAHUE8Phf+rXXglpmSv4XN3eiwfXwvOaAMVjMRmRxsKitl5iZnwpcdbsC4jt16g2r/ihlKzLIYju+XZej4dNMlkftEidyNg24IVimJthXY1H15RZ8Hm7mAM/JZrsxiAVI0A49pWEiUk3cyZcBzq/vVEjHUy4r6IZnKkRvLjqsvqWE95nAGMor+F0GLHWfBCVkuI51EIOknwSB1eTvLgwgRepV4pdy9cdp6iR8TZndPVCikflXYVMlMEJ2bJ2c0Swiq57ORJW6vQwnkxtPudpFRc7tNNDzz4LKEznJxAwGi6pBR7/co2IUgRw1ijLFTHWHQJOjgc7KaduHI0C6a+BJb4Y8IWuIk2u2qCMF1HNKFAUn/J1gTcqtIJcvK5uykpfJFCYc899TmUc8LMKI9nu57m0S44Y2hPPYeW4XSakScsg8bJHMkcXk3Tbs9b4eqiD+kHUhTS2BGfsHadR3d5j8lNhBPzA5e+mE=="
)
