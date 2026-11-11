# db.py
# 全部数据都存在本地 SQLite 文件里：data/qiuzhao.db
# 表结构：jobs（岗位）、profile（个人档案）、plans（每日计划）、
#        knowledge_docs / knowledge_chunks（知识库原文与切片，用于重建向量库）

import json
import os
import sqlite3
from datetime import datetime

# 数据目录，默认 data/，可用环境变量覆盖
DATA_DIR = os.getenv("DATA_DIR", "data")

STATUSES = ["待投递", "已投递", "测评", "面试", "挂"]

# 这些字段在库里存 JSON 字符串，读出来要转成列表
LIST_FIELDS = ["hard_requirements", "tech_stack", "responsibilities",
               "interview_focus", "tags"]

DEFAULT_PROFILE = {
    "basic": {"degree": "", "major": "", "graduation_year": ""},
    "skills_known": [],
    "skills_weak": [],
    "projects": [],
    "interviews": [],
    "notes": "",
}


def _db_path() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, "qiuzhao.db")


def get_conn() -> sqlite3.Connection:
    """每次操作新建一个连接，用完就关，避免多线程共享连接的问题。"""
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    title TEXT,
    job_type TEXT,
    city TEXT,
    salary TEXT,
    deadline TEXT,
    hard_requirements TEXT,
    tech_stack TEXT,
    responsibilities TEXT,
    interview_focus TEXT,
    tags TEXT,
    raw_jd TEXT,
    status TEXT DEFAULT '待投递',
    analysis TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT,
    content TEXT,
    source_text TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    content TEXT,
    chunk_count INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER,
    chunk_index INTEGER,
    text TEXT
);
"""


def init_db():
    """建表，幂等，每次启动都可以调。"""
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        # 档案表初始化一条空档案
        row = conn.execute("SELECT id FROM profile WHERE id = 1").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO profile (id, data, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_PROFILE, ensure_ascii=False), _now()))
            conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ 岗位
def add_job(job: dict) -> int:
    """新增一个岗位。job 里的列表字段会自动转成 JSON 字符串。"""
    conn = get_conn()
    try:
        values = {
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "job_type": job.get("job_type", ""),
            "city": job.get("city", ""),
            "salary": job.get("salary", ""),
            "deadline": job.get("deadline", ""),
            "raw_jd": job.get("raw_jd", ""),
            "status": job.get("status", "待投递") or "待投递",
        }
        for f in LIST_FIELDS:
            values[f] = json.dumps(job.get(f, []) or [], ensure_ascii=False)

        cur = conn.execute(
            f"""INSERT INTO jobs
                ({', '.join(values.keys())}, created_at, updated_at)
                VALUES ({', '.join(['?'] * len(values))}, ?, ?)""",
            list(values.values()) + [_now(), _now()])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _row_to_job(row) -> dict:
    job = dict(row)
    for f in LIST_FIELDS:
        try:
            job[f] = json.loads(job.get(f) or "[]")
        except Exception:
            job[f] = []
    try:
        job["analysis"] = json.loads(job["analysis"]) if job.get("analysis") else None
    except Exception:
        job["analysis"] = None
    return job


def list_jobs(statuses=None, keyword: str = ""):
    """按状态和关键词筛选岗位。statuses 为 None 或空列表表示全部。"""
    conn = get_conn()
    try:
        sql = "SELECT * FROM jobs WHERE 1=1"
        args = []
        if statuses:
            sql += f" AND status IN ({', '.join(['?'] * len(statuses))})"
            args.extend(statuses)
        if keyword.strip():
            sql += " AND (company LIKE ? OR title LIKE ? OR city LIKE ?)"
            kw = f"%{keyword.strip()}%"
            args.extend([kw, kw, kw])
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, args).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def get_job(job_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def update_job_status(job_id: int, status: str):
    conn = get_conn()
    try:
        conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                     (status, _now(), job_id))
        conn.commit()
    finally:
        conn.close()


def save_job_analysis(job_id: int, analysis: dict):
    """把一次岗位分析的 JSON 结果挂到岗位记录上，下次点开还能看到。"""
    conn = get_conn()
    try:
        conn.execute("UPDATE jobs SET analysis = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(analysis, ensure_ascii=False), _now(), job_id))
        conn.commit()
    finally:
        conn.close()


def delete_job(job_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()


def job_summary_text(limit: int = 30) -> str:
    """给大模型看的岗位概要，避免把整库数据都塞进 prompt。"""
    jobs = list_jobs()[:limit]
    if not jobs:
        return "（岗位库还是空的）"
    lines = []
    for j in jobs:
        lines.append(f"- [{j['status']}] {j['company']}｜{j['title']}｜{j['city']}"
                     f"｜截止：{j['deadline'] or '未写'}")
    return "\n".join(lines)


# ------------------------------------------------------------------ 档案
def get_profile() -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
        if not row or not row["data"]:
            return json.loads(json.dumps(DEFAULT_PROFILE))
        data = json.loads(row["data"])
        # 补齐可能缺失的字段，避免旧数据报 KeyError
        for k, v in DEFAULT_PROFILE.items():
            data.setdefault(k, json.loads(json.dumps(v)))
            if isinstance(v, dict):
                for kk, vv in v.items():
                    data[k].setdefault(kk, vv)
        return data
    finally:
        conn.close()


def save_profile(profile: dict):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO profile (id, data, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (json.dumps(profile, ensure_ascii=False), _now()))
        conn.commit()
    finally:
        conn.close()


def merge_profile(old: dict, new: dict) -> dict:
    """把大模型返回的新档案合并进旧档案，保证不丢失任何已有信息。

    规则：字典递归合并；列表取并集去重（旧的在前）；新值为空则不覆盖旧值。
    """
    if isinstance(old, dict) and isinstance(new, dict):
        out = json.loads(json.dumps(old))
        for k, v in new.items():
            if k == "changes":
                continue
            out[k] = merge_profile(out.get(k), v) if k in out else v
        return out

    if isinstance(old, list) and isinstance(new, list):
        out = list(old)
        keys = {json.dumps(x, ensure_ascii=False, sort_keys=True) for x in out}
        for item in new:
            k = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if k not in keys:
                out.append(item)
                keys.add(k)
        return out

    if new is None or (isinstance(new, (str, list, dict)) and len(new) == 0):
        return old
    return new


# ------------------------------------------------------------------ 计划
def add_plan(plan_date: str, content: dict, source_text: str = ""):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO plans (plan_date, content, source_text, created_at) VALUES (?, ?, ?, ?)",
            (plan_date, json.dumps(content, ensure_ascii=False), source_text, _now()))
        conn.commit()
    finally:
        conn.close()


def list_plans(limit: int = 30):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM plans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        plans = []
        for r in rows:
            p = dict(r)
            try:
                p["content"] = json.loads(p["content"])
            except Exception:
                p["content"] = {}
            plans.append(p)
        return plans
    finally:
        conn.close()


# ---------------------------------------------------------------- 知识库
def add_doc(name: str, content: str, chunk_count: int) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO knowledge_docs (name, content, chunk_count, created_at) VALUES (?, ?, ?, ?)",
            (name, content, chunk_count, _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_chunks(doc_id: int, chunks):
    conn = get_conn()
    try:
        conn.executemany(
            "INSERT INTO knowledge_chunks (doc_id, chunk_index, text) VALUES (?, ?, ?)",
            [(doc_id, i, c) for i, c in enumerate(chunks)])
        conn.commit()
    finally:
        conn.close()


def list_docs():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, chunk_count, created_at FROM knowledge_docs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_doc(doc_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM knowledge_docs WHERE id = ?", (doc_id,))
        conn.execute("DELETE FROM knowledge_chunks WHERE doc_id = ?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


def all_chunks():
    """向量库丢了（比如容器重启）时，用这里的原文重建索引。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT c.doc_id, c.chunk_index, c.text, d.name
               FROM knowledge_chunks c JOIN knowledge_docs d ON d.id = c.doc_id
               ORDER BY c.doc_id, c.chunk_index""").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
