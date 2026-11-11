# asr_client.py
# 火山引擎「一句话识别」：上传一段录音，返回整句文字。
# 用的是 HTTP 接口（openspeech/api/v1/asr），一次请求就能拿到结果，不需要长连接。

import base64
import uuid

import requests

from config import get_secret

ASR_URL = "https://openspeech.bytedance.com/api/v1/asr"

# 支持的音频格式
SUPPORTED_FORMATS = {"wav", "mp3", "ogg", "pcm", "amr", "m4a", "aac"}


def transcribe(audio_bytes: bytes, filename: str) -> str:
    """把音频二进制转成文字。

    参数：
        audio_bytes: 上传文件的二进制内容
        filename:    文件名，用来判断格式（wav / mp3 …）
    返回：
        识别出的文字
    """
    appid = get_secret("VOLC_APP_ID")
    # 控制台里的 Access Token；有些账号叫 API Key / Token，键名都可以填这里
    token = get_secret("VOLC_ACCESS_KEY") or get_secret("VOLC_ASR_TOKEN")
    cluster = get_secret("VOLC_ASR_CLUSTER", "volcengine_input_common")

    if not appid or not token:
        raise RuntimeError(
            "没有读到语音识别的密钥。请在 .env / Secrets 里配置 VOLC_APP_ID 和 VOLC_ACCESS_KEY。")

    fmt = filename.rsplit(".", 1)[-1].lower()
    if fmt not in SUPPORTED_FORMATS:
        raise RuntimeError(f"不支持的音频格式：{fmt}，请上传 wav 或 mp3。")

    if len(audio_bytes) > 15 * 1024 * 1024:
        raise RuntimeError("音频太大（超过 15MB）。一句话识别适合 60 秒以内的录音，请先截短。")

    payload = {
        "app": {"appid": appid, "token": token, "cluster": cluster},
        "user": {"uid": "qiuzhao_ai_kanban"},
        "audio": {
            "format": fmt,
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "language": "zh-CN",
            "data": base64.b64encode(audio_bytes).decode(),
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "nbest": 1,
            "workflow": "audio_in,resample,partition,vad,fe,decode",
        },
    }
    headers = {
        # 注意这里的分号：火山的老接口要求 "Bearer;" + 空格 + token
        "Authorization": f"Bearer; {token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(ASR_URL, headers=headers, json=payload, timeout=90)
    except requests.RequestException as e:
        raise RuntimeError(f"调用语音识别接口失败（网络问题）：{e}") from e

    if resp.status_code != 200:
        raise RuntimeError(
            f"语音识别接口返回 {resp.status_code}：{resp.text[:400]}\n"
            "常见原因：VOLC_APP_ID / VOLC_ACCESS_KEY 不对，或该应用没有开通一句话识别服务。")

    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"语音识别返回不是 JSON：{e}；原文：{resp.text[:400]}") from e

    code = data.get("code", -1)
    if code != 0:
        raise RuntimeError(
            f"识别失败（code={code}）：{data.get('message', '未知错误')}\n"
            "提示：一句话识别对音频时长和采样率有要求，建议 16k、60 秒以内的清晰录音。")

    # 结果结构在不同版本略有差异，这里做兼容取值
    result = data.get("result") or {}
    if isinstance(result, list):
        result = result[0] if result else {}

    text = (result.get("text") or "").strip()
    if not text:
        utterances = result.get("utterances") or []
        text = "".join(u.get("text", "") for u in utterances).strip()

    if not text:
        raise RuntimeError("接口返回成功但没有识别到文字，可能是录音太短或全是静音。")
    return text
