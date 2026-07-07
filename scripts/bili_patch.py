"""B站 wbi/playurl 风控 patch。

移植自 BiliNote backend/app/downloaders/bilibili_dm_patch.py。
2026-06 起,B站 x/player/wbi/playurl 网关要求 dm_img_*/web_location 浏览器指纹参数,
否则返回 HTTP 412(裸 yt-dlp 会失败)。本模块 monkey-patch yt-dlp 的
BilibiliBaseIE._download_playinfo,在 wbi 签名前注入 dummy 但格式正确的参数。

幂等且防御性:yt-dlp 缺失或内部结构变化时返回 False,不抛异常。
"""
import base64
import random
import string


def build_dm_img_params() -> dict:
    """返回网关期望的 dummy dm_img_* / web_location 参数。"""
    return {
        "web_location": 1550101,
        "dm_img_list": "[]",
        "dm_img_str": base64.b64encode(
            "".join(random.choices(string.printable, k=random.randint(16, 64))).encode()
        )[:-2].decode(),
        "dm_cover_img_str": base64.b64encode(
            "".join(random.choices(string.printable, k=random.randint(32, 128))).encode()
        )[:-2].decode(),
        "dm_img_inter": '{"ds":[],"wh":[6093,6631,31],"of":[430,760,380]}',
    }


def apply_bilibili_dm_img_patch() -> bool:
    """Monkey-patch yt-dlp 的 BilibiliBaseIE._download_playinfo。返回是否生效。"""
    try:
        from yt_dlp.extractor.bilibili import BilibiliBaseIE
    except Exception:
        return False  # yt-dlp 缺失或模块布局变化

    original = BilibiliBaseIE._download_playinfo
    if getattr(original, "_bili_dm_patched", False):
        return True  # 已 patch(幂等)

    def _patched(self, bvid, cid, headers=None, query=None):
        # dm_* 合并进原方法待 wbi 签名的 query;调用方传入的 query 优先
        merged_query = {**build_dm_img_params(), **(query or {})}
        return original(self, bvid, cid, headers=headers, query=merged_query)

    _patched._bili_dm_patched = True
    BilibiliBaseIE._download_playinfo = _patched
    return True
