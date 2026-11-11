# llm_client.py
# 调用火山方舟（豆包）的对话接口，四个业务函数都强制返回 JSON。
# 用的是 OpenAI 兼容的 HTTP 接口，所以只依赖 requests，不需要额外 SDK。

import json
import re

import requests

import prompts
from config import get_secret

# 方舟接口地址（一般不用改）
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"


def _model() -> str:
    # ARK_MODEL 可以填模型名（如 doubao-pro-32k），也可以填推理接入点 ID（ep-xxxx）
    return get_secret("ARK_MODEL", "doubao-pro-32k")


def _clean_json_text(text: str) -> str:
    """模型偶尔会裹 Markdown 代码块或加解释，这里做一次清洗。"""
    text = (text or "").strip()

    # 去掉 ```json ... ``` 包裹
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    # 只保留第一个 { 到最后一个 } 之间的内容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    # 去掉对象/数组结尾多余的逗号（模型常见小毛病）
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def chat_json(system_prompt: str, user_content: str, temperature: float = 0.3,
              max_tokens: int = 4096) -> dict:
    """一次对话调用，返回解析好的 dict。"""
    api_key = get_secret("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("没有读到 ARK_API_KEY。请在 .env（本地）或 Secrets（线上）里配置。")

    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(ARK_BASE_URL, headers=headers, json=payload, timeout=120)
    except requests.RequestException as e:
        raise RuntimeError(f"调用方舟接口失败（网络问题）：{e}") from e

    if resp.status_code != 200:
        raise RuntimeError(
            f"方舟接口返回 {resp.status_code}：{resp.text[:500]}\n"
            "常见原因：ARK_API_KEY 不对、ARK_MODEL 填的模型/接入点不存在、或该模型没开通。")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"解析方舟返回结构失败：{e}；原始返回：{resp.text[:500]}") from e

    try:
        return json.loads(_clean_json_text(content))
    except Exception as e:
        raise RuntimeError(
            f"模型没有返回合法 JSON：{e}\n原始内容：{content[:800]}") from e


# ------------------------------------------------------------------ 业务函数
def parse_jd(jd_text: str) -> dict:
    """把 JD 原文解析成结构化字段。"""
    user = prompts.JD_PARSE_USER_TEMPLATE.format(jd_text=jd_text.strip()[:8000])
    result = chat_json(prompts.JD_PARSE_SYSTEM, user, temperature=0.1, max_tokens=2048)

    # 兜底：保证字段齐全且类型正确
    out = {
        "company": str(result.get("company", "") or ""),
        "title": str(result.get("title", "") or ""),
        "job_type": str(result.get("job_type", "") or ""),
        "city": str(result.get("city", "") or ""),
        "salary": str(result.get("salary", "") or ""),
        "deadline": str(result.get("deadline", "") or ""),
    }
    for f in ["hard_requirements", "tech_stack", "responsibilities",
              "interview_focus", "tags"]:
        value = result.get(f, [])
        if isinstance(value, str):
            value = [v.strip() for v in re.split(r"\n|、|;|；", value) if v.strip()]
        out[f] = [str(v).strip() for v in (value or []) if str(v).strip()]
    return out


def _format_refs(refs) -> str:
    if not refs:
        return "（知识库没有检索到相关资料）"
    blocks = []
    for i, r in enumerate(refs, 1):
        blocks.append(f"[资料{i}｜来源：{r.get('doc_name', '未知')}]\n{r.get('text', '')}")
    return "\n\n".join(blocks)


def analyze_job(job: dict, profile: dict, refs) -> dict:
    """结合 JD + 个人档案 + 知识库片段，输出匹配分析。"""
    job_view = {k: v for k, v in job.items() if k not in ("analysis", "raw_jd")}
    user = prompts.JOB_ANALYZE_USER_TEMPLATE.format(
        job_json=json.dumps(job_view, ensure_ascii=False, indent=1),
        profile_json=json.dumps(profile, ensure_ascii=False, indent=1),
        rag_context=_format_refs(refs),
    )
    result = chat_json(prompts.JOB_ANALYZE_SYSTEM, user, temperature=0.3, max_tokens=4096)

    # 分数兜底
    try:
        score = int(float(result.get("match_score", 0)))
    except Exception:
        score = 0
    result["match_score"] = max(0, min(100, score))
    return result


def update_profile(profile: dict, transcript: str) -> dict:
    """根据语音转写文本增量更新档案，返回"合并后的档案 + changes"。"""
    user = prompts.PROFILE_UPDATE_USER_TEMPLATE.format(
        profile_json=json.dumps(profile, ensure_ascii=False, indent=1),
        transcript=transcript.strip()[:4000],
    )
    return chat_json(prompts.PROFILE_UPDATE_SYSTEM, user, temperature=0.2, max_tokens=3072)


def generate_plan(profile: dict, job_summary: str, transcript: str, today: str) -> dict:
    """生成当天的秋招计划。"""
    user = prompts.PLAN_GENERATE_USER_TEMPLATE.format(
        today=today,
        profile_json=json.dumps(profile, ensure_ascii=False, indent=1),
        job_summary=job_summary,
        transcript=transcript.strip()[:4000],
    )
    result = chat_json(prompts.PLAN_GENERATE_SYSTEM, user, temperature=0.4, max_tokens=2048)
    result.setdefault("date", today)
    result.setdefault("tasks", [])
    return result
