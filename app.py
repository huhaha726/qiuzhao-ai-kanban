# app.py
# 秋招 AI 看板 —— Streamlit 主程序
# 五个 Tab：JD解析&岗位库 / 个人求职档案 / 语音上传ASR / 岗位RAG分析 / RAG知识库上传

import json
import os
from datetime import date

import streamlit as st

import asr_client
import db
import llm_client
import rag_client
from config import has_asr_key, has_llm_key

# ------------------------------------------------------------------ 页面基础设置
st.set_page_config(page_title="秋招 AI 看板", page_icon="🎯", layout="wide")

db.init_db()


# ------------------------------------------------------------------ 小工具函数
def lines_to_list(text: str):
    """文本框里一行一条 → 列表。"""
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


def list_to_lines(items):
    """列表 → 一行一条的文本，用于回填文本框。"""
    return "\n".join(items or [])


@st.cache_resource(show_spinner="正在恢复知识库向量索引…")
def ensure_index():
    """容器重启后向量库可能丢了，用 SQLite 里的原文自动重建一次。"""
    try:
        if rag_client.count() == 0:
            rows = db.all_chunks()
            if rows:
                return rag_client.rebuild_from_chunks(rows)
    except Exception:
        # 模型下载失败等情况不影响其他功能
        pass
    return 0


def render_plan(plan: dict, key_prefix: str = ""):
    """统一渲染一份「每日计划」JSON。"""
    if not plan:
        return
    st.markdown(f"#### {plan.get('date', '')}　{plan.get('focus', '')}")
    for i, task in enumerate(plan.get("tasks", [])):
        with st.container(border=True):
            st.markdown(f"**{task.get('time_block', '')}　{task.get('task', '')}**")
            if task.get("output"):
                st.caption(f"产出：{task['output']}｜优先级：{task.get('priority', '-')}")
    if plan.get("kpi"):
        st.markdown("**今日 KPI**")
        for k in plan["kpi"]:
            st.markdown(f"- {k}")
    if plan.get("note"):
        st.caption(f"提醒：{plan['note']}")


def render_analysis(result: dict, refs=None):
    """统一渲染岗位分析结果。"""
    score = result.get("match_score", 0)
    c1, c2 = st.columns([1, 3])
    with c1:
        st.metric("匹配分数", f"{score} / 100")
    with c2:
        st.info(result.get("score_reason", ""))

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("##### 💪 个人优势")
        for s in result.get("strengths", []) or []:
            with st.container(border=True):
                st.markdown(f"**{s.get('point', '')}**")
                if s.get("evidence"):
                    st.caption(f"依据：{s['evidence']}")
                if s.get("why_it_matters"):
                    st.caption(f"意义：{s['why_it_matters']}")
    with col_right:
        st.markdown("##### ⚠️ 短板")
        for w in result.get("weaknesses", []) or []:
            with st.container(border=True):
                st.markdown(f"**{w.get('point', '')}**")
                if w.get("impact"):
                    st.caption(f"影响：{w['impact']}")
                if w.get("how_to_fix"):
                    st.caption(f"怎么补：{w['how_to_fix']}")

    st.markdown("##### 📅 3 天学习计划")
    days = result.get("three_day_plan", []) or []
    if days:
        cols = st.columns(len(days))
        for col, day in zip(cols, days):
            with col:
                with st.container(border=True):
                    st.markdown(f"**Day {day.get('day', '')}｜{day.get('goal', '')}**")
                    if day.get("content"):
                        st.markdown("学习内容")
                        for x in day["content"]:
                            st.markdown(f"- {x}")
                    if day.get("materials"):
                        st.markdown("参考资料")
                        for x in day["materials"]:
                            st.markdown(f"- {x}")
                    if day.get("selftest"):
                        st.markdown("自测任务")
                        for x in day["selftest"]:
                            st.markdown(f"- {x}")

    advice = result.get("apply_advice") or {}
    if advice:
        st.markdown("##### 📮 投递建议")
        with st.container(border=True):
            st.markdown(f"**现在适合投吗：**{advice.get('should_apply_now', '-')}")
            if advice.get("timing"):
                st.markdown(f"**投递时机：**{advice['timing']}")
            if advice.get("must_fix_first"):
                st.markdown("**投递前要先补的：**")
                for x in advice["must_fix_first"]:
                    st.markdown(f"- {x}")
            if advice.get("risks"):
                st.markdown("**风险提示：**")
                for x in advice["risks"]:
                    st.markdown(f"- {x}")

    if refs:
        with st.expander(f"📚 检索到的参考资料（{len(refs)} 段）"):
            for i, r in enumerate(refs, 1):
                st.markdown(f"**资料 {i}｜{r.get('doc_name', '未知')}**")
                st.caption(f"相似度距离：{r.get('distance')}")
                st.text(r.get("text", "")[:1200])


# ------------------------------------------------------------------ 侧边栏
with st.sidebar:
    st.markdown("### ⚙️ 配置检查")
    if has_llm_key():
        st.success("豆包（方舟）密钥已配置")
    else:
        st.error("缺少 ARK_API_KEY，JD 解析 / 分析 / 计划都用不了")
    if has_asr_key():
        st.success("语音识别密钥已配置")
    else:
        st.warning("缺少 VOLC_APP_ID / VOLC_ACCESS_KEY，语音转写用不了")

    st.markdown("---")
    st.markdown("### 💾 数据")
    st.caption("岗位、档案、计划都存在本地 SQLite：data/qiuzhao.db")
    db_file = os.path.join(db.DATA_DIR, "qiuzhao.db")
    if os.path.exists(db_file):
        with open(db_file, "rb") as f:
            st.download_button("下载数据备份", f.read(), file_name="qiuzhao.db")
    st.caption("免费托管环境的磁盘重启后会被重置，重要数据记得定期备份。")

st.title("🎯 秋招 AI 看板")
st.caption("JD 解析 · 岗位库看板 · 求职档案 · 语音速记 · RAG 匹配分析")

tab_jd, tab_profile, tab_asr, tab_analyze, tab_kb = st.tabs(
    ["JD解析 & 岗位库", "个人求职档案", "语音上传 ASR", "岗位 RAG 分析", "RAG 知识库上传"])


# ================================================================== Tab 1
with tab_jd:
    st.subheader("① 粘贴 JD，自动解析")
    jd_text = st.text_area(
        "岗位 JD 原文", height=240, key="jd_input",
        placeholder="把招聘网站上的 JD 全文粘贴到这里，点下面的按钮解析…")

    if st.button("解析 JD", type="primary", key="btn_parse_jd"):
        if not jd_text.strip():
            st.warning("先把 JD 粘贴进来。")
        else:
            with st.spinner("豆包正在解析 JD…"):
                try:
                    st.session_state["parsed_jd"] = llm_client.parse_jd(jd_text)
                except Exception as e:
                    st.error(str(e))

    # 解析结果 → 可人工修改再入库
    parsed = st.session_state.get("parsed_jd")
    if parsed:
        st.markdown("**解析结果**（可以直接修改，确认后保存到岗位库）")
        with st.form("form_save_job"):
            c1, c2, c3 = st.columns(3)
            company = c1.text_input("公司", parsed.get("company", ""))
            title = c2.text_input("岗位名称", parsed.get("title", ""))
            job_type = c3.text_input("岗位类型", parsed.get("job_type", ""))

            c4, c5, c6 = st.columns(3)
            city = c4.text_input("城市", parsed.get("city", ""))
            salary = c5.text_input("薪资", parsed.get("salary", ""))
            deadline = c6.text_input("截止时间", parsed.get("deadline", ""))

            hard_req = st.text_area("硬性要求（一行一条）",
                                    list_to_lines(parsed.get("hard_requirements")), height=100)
            tech = st.text_area("技术栈（一行一条）",
                                list_to_lines(parsed.get("tech_stack")), height=100)
            duty = st.text_area("岗位职责（一行一条）",
                                list_to_lines(parsed.get("responsibilities")), height=130)
            focus = st.text_area("面试重点（一行一条）",
                                 list_to_lines(parsed.get("interview_focus")), height=130)
            tags = st.text_area("标签（一行一条）", list_to_lines(parsed.get("tags")), height=80)

            saved = st.form_submit_button("保存到岗位库", type="primary")
            if saved:
                job = {
                    "company": company, "title": title, "job_type": job_type,
                    "city": city, "salary": salary, "deadline": deadline,
                    "hard_requirements": lines_to_list(hard_req),
                    "tech_stack": lines_to_list(tech),
                    "responsibilities": lines_to_list(duty),
                    "interview_focus": lines_to_list(focus),
                    "tags": lines_to_list(tags),
                    "raw_jd": jd_text,
                }
                db.add_job(job)
                st.session_state.pop("parsed_jd", None)
                st.success(f"已保存：{company} · {title}")
                st.rerun()

    st.divider()

    # ---------------- 岗位库
    st.subheader("② 岗位库")
    all_jobs = db.list_jobs()
    if not all_jobs:
        st.caption("岗位库还是空的，先在上面解析并保存一个 JD。")
    else:
        f1, f2, f3 = st.columns([2, 2, 2])
        status_filter = f1.multiselect("按状态筛选", db.STATUSES, default=[])
        keyword = f2.text_input("搜索公司 / 岗位 / 城市", "")
        view = f3.radio("展示方式", ["看板视图", "列表视图"], horizontal=True)

        jobs = db.list_jobs(status_filter, keyword)
        st.caption(f"共 {len(jobs)} 个岗位")

        if view == "看板视图":
            cols = st.columns(len(db.STATUSES))
            for col, status in zip(cols, db.STATUSES):
                with col:
                    group = [j for j in jobs if j["status"] == status]
                    st.markdown(f"**{status} · {len(group)}**")
                    for j in group:
                        with st.container(border=True):
                            st.markdown(f"**{j['company']}**")
                            st.caption(j["title"])
                            st.caption(f"{j['city']}｜截止 {j['deadline'] or '未写'}")
        else:
            for j in jobs:
                with st.expander(f"{j['company']} · {j['title']}　［{j['status']}］"):
                    if j.get("city") or j.get("salary"):
                        st.caption(f"{j.get('city', '')}｜{j.get('salary', '')}｜截止 {j.get('deadline') or '未写'}")
                    if j.get("tech_stack"):
                        st.markdown("**技术栈：**" + "、".join(j["tech_stack"]))
                    if j.get("hard_requirements"):
                        st.markdown("**硬性要求：**")
                        for x in j["hard_requirements"]:
                            st.markdown(f"- {x}")
                    if j.get("responsibilities"):
                        st.markdown("**岗位职责：**")
                        for x in j["responsibilities"]:
                            st.markdown(f"- {x}")
                    if j.get("interview_focus"):
                        st.markdown("**面试重点：**")
                        for x in j["interview_focus"]:
                            st.markdown(f"- {x}")
                    if j.get("tags"):
                        st.caption("标签：" + " / ".join(j["tags"]))

                    st.divider()
                    cur = j["status"] if j["status"] in db.STATUSES else db.STATUSES[0]
                    new_status = st.selectbox(
                        "投递状态", db.STATUSES, index=db.STATUSES.index(cur),
                        key=f"status_{j['id']}")
                    b1, b2 = st.columns(2)
                    if b1.button("更新状态", key=f"upd_{j['id']}"):
                        db.update_job_status(j["id"], new_status)
                        st.rerun()
                    if b2.button("删除这个岗位", key=f"del_{j['id']}"):
                        db.delete_job(j["id"])
                        st.rerun()


# ================================================================== Tab 2
with tab_profile:
    st.subheader("个人求职档案")
    st.caption("这些信息会作为「我的现状」提供给 AI，用来算匹配分和生成计划。")

    profile = db.get_profile()
    basic = profile.get("basic", {})

    with st.form("form_profile_main"):
        c1, c2, c3 = st.columns(3)
        degree = c1.text_input("学历", basic.get("degree", ""), placeholder="本科 / 硕士")
        major = c2.text_input("专业", basic.get("major", ""))
        grad_year = c3.text_input("毕业年份", basic.get("graduation_year", ""), placeholder="2026")

        known = st.text_area("已掌握的技术（一行一个）",
                             list_to_lines(profile.get("skills_known")), height=130)
        weak = st.text_area("薄弱的技术（一行一个）",
                            list_to_lines(profile.get("skills_weak")), height=130)
        notes = st.text_area("长期备注（求职意向、偏好、约定事项等）",
                             profile.get("notes", ""), height=120)

        if st.form_submit_button("保存档案", type="primary"):
            profile["basic"] = {"degree": degree, "major": major,
                                "graduation_year": grad_year}
            profile["skills_known"] = lines_to_list(known)
            profile["skills_weak"] = lines_to_list(weak)
            profile["notes"] = notes
            db.save_profile(profile)
            st.success("已保存。")

    # ---------------- 项目经历
    st.markdown("#### 项目经历")
    for i, proj in enumerate(profile.get("projects", [])):
        with st.expander(f"项目 {i + 1}｜{proj.get('name', '（未命名）')}"):
            with st.form(f"form_proj_{i}"):
                name = st.text_input("项目名称", proj.get("name", ""))
                role = st.text_input("担任角色", proj.get("role", ""))
                desc = st.text_area("项目描述", proj.get("desc", ""), height=90)
                tech = st.text_input("技术栈（用、分隔）", "、".join(proj.get("tech", []) or []))
                highlights = st.text_area("亮点（一行一条）",
                                          list_to_lines(proj.get("highlights")), height=90)
                s1, s2 = st.columns(2)
                save_it = s1.form_submit_button("保存这个项目")
                del_it = s2.form_submit_button("删除这个项目")
                if save_it:
                    profile["projects"][i] = {
                        "name": name, "role": role, "desc": desc,
                        "tech": [x.strip() for x in tech.split("、") if x.strip()],
                        "highlights": lines_to_list(highlights),
                    }
                    db.save_profile(profile)
                    st.success("项目已更新。")
                    st.rerun()
                if del_it:
                    profile["projects"].pop(i)
                    db.save_profile(profile)
                    st.rerun()

    with st.expander("＋ 新增一个项目"):
        with st.form("form_proj_new", clear_on_submit=True):
            name = st.text_input("项目名称")
            role = st.text_input("担任角色")
            desc = st.text_area("项目描述", height=90)
            tech = st.text_input("技术栈（用、分隔）")
            highlights = st.text_area("亮点（一行一条）", height=90)
            if st.form_submit_button("添加"):
                profile.setdefault("projects", []).append({
                    "name": name, "role": role, "desc": desc,
                    "tech": [x.strip() for x in tech.split("、") if x.strip()],
                    "highlights": lines_to_list(highlights),
                })
                db.save_profile(profile)
                st.success("已添加。")
                st.rerun()

    # ---------------- 面试记录
    st.markdown("#### 面试记录")
    for i, rec in enumerate(profile.get("interviews", [])):
        with st.expander(f"{rec.get('date', '')}｜{rec.get('company', '')}｜{rec.get('round', '')}"):
            with st.form(f"form_int_{i}"):
                c1, c2, c3 = st.columns(3)
                d = c1.text_input("日期", rec.get("date", ""))
                comp = c2.text_input("公司", rec.get("company", ""))
                rnd = c3.text_input("轮次", rec.get("round", ""))
                res = st.text_input("结果（通过 / 挂了 / 待定）", rec.get("result", ""))
                review = st.text_area("复盘", rec.get("review", ""), height=100)
                s1, s2 = st.columns(2)
                if s1.form_submit_button("保存这条"):
                    profile["interviews"][i] = {
                        "date": d, "company": comp, "round": rnd,
                        "result": res, "review": review}
                    db.save_profile(profile)
                    st.success("已保存。")
                    st.rerun()
                if s2.form_submit_button("删除这条"):
                    profile["interviews"].pop(i)
                    db.save_profile(profile)
                    st.rerun()

    with st.expander("＋ 新增面试记录"):
        with st.form("form_int_new", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            d = c1.text_input("日期", placeholder="2026-11-05")
            comp = c2.text_input("公司")
            rnd = c3.text_input("轮次", placeholder="一面 / 二面 / HR面")
            res = st.text_input("结果")
            review = st.text_area("复盘", height=100)
            if st.form_submit_button("添加"):
                profile.setdefault("interviews", []).append({
                    "date": d, "company": comp, "round": rnd,
                    "result": res, "review": review})
                db.save_profile(profile)
                st.success("已添加。")
                st.rerun()

    # ---------------- 直接编辑 JSON
    with st.expander("高级：直接编辑档案 JSON"):
        raw = st.text_area("档案 JSON", json.dumps(profile, ensure_ascii=False, indent=2),
                          height=300, key="profile_json_editor")
        if st.button("保存 JSON"):
            try:
                db.save_profile(json.loads(raw))
                st.success("已保存。")
                st.rerun()
            except Exception as e:
                st.error(f"JSON 格式有问题：{e}")


# ================================================================== Tab 3
with tab_asr:
    st.subheader("语音速记 → 更新档案 / 生成今日计划")
    st.caption("录一段语音说今天做了什么、面了哪家、接下来要干什么，转成文字后交给 AI 处理。")

    audio_file = st.file_uploader("上传录音（wav / mp3）", type=["wav", "mp3"])

    if audio_file is not None and st.button("转写成文字", type="primary", key="btn_asr"):
        with st.spinner("正在识别语音…"):
            try:
                st.session_state["asr_text_ui"] = asr_client.transcribe(
                    audio_file.getvalue(), audio_file.name)
            except Exception as e:
                st.error(str(e))

    transcript = st.text_area("转写文本（可以直接改）", height=180, key="asr_text_ui")

    b1, b2 = st.columns(2)
    if b1.button("① 用这段文字更新求职档案"):
        if not transcript.strip():
            st.warning("先转写或者手动输入一段文字。")
        else:
            with st.spinner("豆包正在合并进档案…"):
                try:
                    result = llm_client.update_profile(db.get_profile(), transcript)
                    db.save_profile(db.merge_profile(db.get_profile(), result))
                    st.success("档案已更新（原有信息不会被覆盖）。")
                    changes = result.get("changes") or []
                    if changes:
                        st.markdown("**本次改动：**")
                        for c in changes:
                            st.markdown(f"- {c.get('field', '')}：{c.get('detail', '')}")
                except Exception as e:
                    st.error(str(e))

    if b2.button("② 生成今日秋招计划"):
        if not transcript.strip():
            st.warning("先转写或者手动输入一段文字。")
        else:
            with st.spinner("豆包正在排今天的计划…"):
                try:
                    today = date.today().strftime("%Y-%m-%d")
                    plan = llm_client.generate_plan(
                        db.get_profile(), db.job_summary_text(), transcript, today)
                    db.add_plan(plan.get("date", today), plan, transcript)
                    st.session_state["last_plan"] = plan
                    st.success("计划已生成并保存。")
                except Exception as e:
                    st.error(str(e))

    if st.session_state.get("last_plan"):
        st.divider()
        render_plan(st.session_state["last_plan"])

    st.divider()
    plans = db.list_plans()
    with st.expander(f"📆 历史计划（{len(plans)} 份）"):
        if not plans:
            st.caption("还没有生成过计划。")
        for p in plans:
            with st.expander(f"{p['plan_date']}｜{(p['content'] or {}).get('focus', '')}（{p['created_at']}）"):
                render_plan(p["content"])


# ================================================================== Tab 4
with tab_analyze:
    st.subheader("岗位 RAG 分析")
    st.caption("结构化 JD + 我的档案 + 知识库资料 → 匹配分、优势、短板、3 天冲刺计划。")

    jobs = db.list_jobs()
    if not jobs:
        st.info("岗位库是空的，先去第一个 Tab 解析并保存一个 JD。")
    else:
        options = {f"{j['company']} · {j['title']}（{j['city']}｜{j['status']}）": j["id"]
                   for j in jobs}
        label = st.selectbox("选择要分析的岗位", list(options.keys()))
        job_id = options[label]
        job = db.get_job(job_id)

        with st.expander("岗位信息速览"):
            st.json({k: job.get(k) for k in
                     ["company", "title", "job_type", "city", "salary", "deadline",
                      "tech_stack", "hard_requirements"]})

        if st.button("开始分析", type="primary", key="btn_analyze"):
            ensure_index()
            profile = db.get_profile()
            # 检索词：岗位标题 + 技术栈 + 我的薄弱项，保证召回的是相关八股/面经
            query = " ".join([
                job.get("title", ""),
                " ".join(job.get("tech_stack", [])[:10]),
                " ".join(job.get("interview_focus", [])[:5]),
                " ".join(profile.get("skills_weak", [])[:5]),
            ]).strip()

            with st.spinner("正在检索知识库并让豆包做分析…"):
                try:
                    refs = rag_client.search(query, top_k=5)
                    result = llm_client.analyze_job(job, profile, refs)
                    db.save_job_analysis(job_id, result)
                    st.session_state["current_analysis"] = {
                        "job_id": job_id, "result": result, "refs": refs}
                except Exception as e:
                    st.error(str(e))

        current = st.session_state.get("current_analysis")
        if current and current["job_id"] == job_id:
            st.divider()
            render_analysis(current["result"], current.get("refs"))
        elif job.get("analysis"):
            st.divider()
            st.caption("显示上次已保存的分析结果（参考资料未缓存，重新分析可再次检索）。")
            render_analysis(job["analysis"], None)


# ================================================================== Tab 5
with tab_kb:
    st.subheader("RAG 知识库")
    st.caption("上传八股、面经、技术笔记（txt / md），自动切片进 Chroma 向量库，分析岗位时自动检索。")

    files = st.file_uploader("上传文档（可多选）", type=["txt", "md", "markdown"],
                             accept_multiple_files=True)

    if st.button("切分并存入知识库", type="primary", key="btn_kb_add"):
        if not files:
            st.warning("先选择文件。")
        else:
            ensure_index()
            ok, fail = 0, []
            with st.spinner("正在切分并生成向量…（第一次会下载向量模型，稍慢）"):
                for f in files:
                    try:
                        raw = f.getvalue()
                        try:
                            content = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            content = raw.decode("gbk", errors="ignore")
                        chunks = rag_client.split_text(content)
                        if not chunks:
                            fail.append(f"{f.name}：内容为空")
                            continue
                        doc_id = db.add_doc(f.name, content, len(chunks))
                        db.add_chunks(doc_id, chunks)
                        rag_client.add_document(doc_id, f.name, chunks)
                        ok += 1
                    except Exception as e:
                        fail.append(f"{f.name}：{e}")
            st.success(f"成功入库 {ok} 个文件。")
            for msg in fail:
                st.error(msg)
            if ok:
                st.rerun()

    st.divider()
    docs = db.list_docs()
    if not docs:
        st.caption("知识库还是空的。")
    else:
        st.caption(f"已入库 {len(docs)} 份文档，共 "
                   f"{sum(d['chunk_count'] or 0 for d in docs)} 个片段。")
        for d in docs:
            with st.expander(f"{d['name']}（{d['chunk_count']} 段｜{d['created_at']}）"):
                if st.button("删除这份文档", key=f"kb_del_{d['id']}"):
                    rag_client.delete_document(d["id"], d["chunk_count"])
                    db.delete_doc(d["id"])
                    st.rerun()
