"""B站必剪(BCut)云端 ASR。

移植自 BiliNote backend/app/transcriber/bcut.py,去除 logger/timeit/events 耦合。
免 API Key,仅需 requests。输入为本地音频文件路径。
"""
import json
import time

import requests

from models import TranscriptResult, TranscriptSegment

API_BASE = "https://member.bilibili.com/x/bcut/rubick-interface"
API_REQ_UPLOAD = API_BASE + "/resource/create"
API_COMMIT_UPLOAD = API_BASE + "/resource/create/complete"
API_CREATE_TASK = API_BASE + "/task"
API_QUERY_RESULT = API_BASE + "/task/result"

HEADERS = {
    "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
    "Content-Type": "application/json",
}

MAX_POLL = 120  # 轮询上限(次),每次间隔 1s


def transcript(file_path: str) -> TranscriptResult:
    """对本地音频文件执行 BCut ASR,返回 TranscriptResult。失败抛 RuntimeError。"""
    session = requests.Session()
    with open(file_path, "rb") as f:
        file_binary = f.read()
    if not file_binary:
        raise RuntimeError(f"无法读取音频文件: {file_path}")

    download_url = _upload(session, file_binary)
    task_id = _create_task(session, download_url)
    result_json = _poll_result(session, task_id)

    segments = []
    full_text = ""
    for u in result_json.get("utterances", []):
        text = u.get("transcript", "").strip()
        start = float(u.get("start_time", 0)) / 1000.0  # 毫秒 → 秒
        end = float(u.get("end_time", 0)) / 1000.0
        full_text += text + " "
        segments.append(TranscriptSegment(start=start, end=end, text=text))

    return TranscriptResult(
        language=result_json.get("language", "zh"),
        full_text=full_text.strip(),
        segments=segments,
        source="bcut",
    )


def _upload(session: requests.Session, file_binary: bytes) -> str:
    """申请上传 → 分片 PUT → 提交,返回 download_url。"""
    payload = json.dumps({
        "type": 2, "name": "audio.mp3", "size": len(file_binary),
        "ResourceFileType": "mp3", "model_id": "8",
    })
    resp = session.post(API_REQ_UPLOAD, data=payload, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()["data"]

    in_boss_key = data["in_boss_key"]
    resource_id = data["resource_id"]
    upload_id = data["upload_id"]
    upload_urls = data["upload_urls"]
    per_size = data["per_size"]
    clips = len(upload_urls)

    etags = []
    for clip in range(clips):
        start_range = clip * per_size
        end_range = min((clip + 1) * per_size, len(file_binary))
        r = session.put(
            upload_urls[clip],
            data=file_binary[start_range:end_range],
            headers={"Content-Type": "application/octet-stream"},
        )
        r.raise_for_status()
        etags.append(r.headers.get("Etag", "").strip('"'))

    commit = json.dumps({
        "InBossKey": in_boss_key, "ResourceId": resource_id,
        "Etags": ",".join(etags), "UploadId": upload_id, "model_id": "8",
    })
    resp = session.post(API_COMMIT_UPLOAD, data=commit, headers=HEADERS)
    resp.raise_for_status()
    cdata = resp.json()
    if cdata.get("code") != 0:
        raise RuntimeError(f"BCut 上传提交失败: {cdata.get('message', '未知错误')}")
    return cdata["data"]["download_url"]


def _create_task(session: requests.Session, download_url: str) -> str:
    resp = session.post(
        API_CREATE_TASK,
        json={"resource": download_url, "model_id": "8"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"BCut 创建任务失败: {data.get('message', '未知错误')}")
    return data["data"]["task_id"]


def _poll_result(session: requests.Session, task_id: str) -> dict:
    for _ in range(MAX_POLL):
        resp = session.get(
            API_QUERY_RESULT,
            params={"model_id": 7, "task_id": task_id},
            headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"BCut 查询失败: {data.get('message', '未知错误')}")
        task = data["data"]
        if task["state"] == 4:  # 完成
            return json.loads(task["result"])
        if task["state"] == 3:  # 失败
            raise RuntimeError("BCut ASR 任务失败(state=3)")
        time.sleep(1)
    raise RuntimeError(f"BCut ASR 超时({MAX_POLL}s 内未完成)")
