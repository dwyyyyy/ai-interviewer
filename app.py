from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from src.browser_tts import build_browser_tts_html, load_browser_tts_config
from src.config_parser import build_interview_config
from src.document_loader import load_document
from src.evaluator import evaluate_answer
from src.flow_controller import InterviewFlowController
from src.interviewer import generate_next_question
from src.llm_client import LLMClient
from src.matcher import build_match_analysis
from src.memory import InterviewMemory
from src.planner import build_interview_plan
from src.profile import build_final_profile, build_pre_interview_brief
from src.reporter import build_report
from src.role_builder import build_interviewer_role
from src.storage import InterviewStore
from src.structurer import structure_jd, structure_resume
from src.xingyun_avatar import build_xingyun_avatar_html, load_xingyun_avatar_config


st.set_page_config(page_title="AI 模拟面试官", page_icon="AI", layout="wide")


def render_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #18202f;
            --muted: #657084;
            --line: #d6dde8;
            --panel: #ffffff;
            --soft: #f6f8fb;
            --soft-2: #eef3f7;
            --teal: #0f766e;
            --blue: #2458a7;
            --amber: #a86412;
            --rose: #b4233a;
            --shadow: 0 10px 28px rgba(24, 32, 47, 0.07);
        }
        .stApp {
            background:
                linear-gradient(180deg, #f7f9fc 0%, #eef3f7 100%);
        }
        .block-container {
            padding-top: 1.35rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }
        h1, h2, h3 {
            color: var(--ink);
            letter-spacing: 0;
        }
        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
            box-shadow: 0 4px 14px rgba(24, 32, 47, 0.035);
        }
        [data-testid="stMetricLabel"] {
            color: var(--muted);
        }
        .hero {
            border: 1px solid #243044;
            border-radius: 8px;
            padding: 24px 26px;
            background: linear-gradient(135deg, #18202f 0%, #26364f 100%);
            box-shadow: var(--shadow);
            margin-bottom: 16px;
        }
        .hero-title {
            font-size: 30px;
            line-height: 1.2;
            font-weight: 780;
            color: #ffffff;
            margin: 0 0 8px 0;
        }
        .hero-subtitle {
            color: #dbe5f2;
            font-size: 15px;
            margin: 0;
            max-width: 860px;
        }
        .panel {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px;
            background: var(--panel);
            margin-bottom: 14px;
            box-shadow: var(--shadow);
        }
        .panel-soft {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
            background: var(--soft);
            margin-bottom: 14px;
        }
        .topline {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
            background: rgba(255, 255, 255, 0.82);
            margin-bottom: 14px;
        }
        .topline strong {
            color: var(--ink);
        }
        .topline span {
            color: var(--muted);
            font-size: 13px;
        }
        .question {
            border: 1px solid #b8d9d4;
            border-left: 5px solid var(--teal);
            background: linear-gradient(180deg, #f2fbf9 0%, #ffffff 100%);
            border-radius: 8px;
            padding: 18px 20px;
            margin: 8px 0 10px 0;
            color: var(--ink);
            font-size: 17px;
            line-height: 1.65;
            box-shadow: var(--shadow);
        }
        .question-label {
            color: #0f766e;
            font-size: 12px;
            font-weight: 800;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .question-meta {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin: 10px 0 14px 0;
        }
        .tag {
            display: inline-block;
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 4px 10px;
            margin: 0 6px 6px 0;
            color: var(--ink);
            background: #ffffff;
            font-size: 12px;
            line-height: 1.4;
        }
        .tag-teal {
            border-color: #99f6e4;
            background: #f0fdfa;
            color: #115e59;
        }
        .tag-amber {
            border-color: #fde68a;
            background: #fffbeb;
            color: #92400e;
        }
        .tag-rose {
            border-color: #fecdd3;
            background: #fff1f2;
            color: #9f1239;
        }
        .muted {
            color: var(--muted);
            font-size: 13px;
        }
        .section-label {
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .subtle-box {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
            padding: 13px 14px;
            margin-bottom: 10px;
        }
        .subtle-box-title {
            color: var(--ink);
            font-size: 14px;
            font-weight: 740;
            margin-bottom: 5px;
        }
        .subtle-box-body {
            color: var(--muted);
            font-size: 13px;
            line-height: 1.55;
        }
        .input-panel {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px;
            background: rgba(255, 255, 255, 0.9);
            box-shadow: var(--shadow);
        }
        .input-title {
            color: var(--ink);
            font-size: 18px;
            font-weight: 780;
            margin-bottom: 4px;
        }
        .input-subtitle {
            color: var(--muted);
            font-size: 13px;
            line-height: 1.55;
            margin-bottom: 14px;
        }
        .report-callout {
            border: 1px solid #c7d7ec;
            border-left: 5px solid var(--blue);
            border-radius: 8px;
            background: #f7fbff;
            padding: 16px 18px;
            color: var(--ink);
            line-height: 1.65;
            margin-bottom: 14px;
        }
        div.stButton > button {
            border-radius: 8px;
            font-weight: 650;
            min-height: 42px;
        }
        div.stDownloadButton > button {
            border-radius: 8px;
            font-weight: 650;
        }
        textarea {
            border-radius: 8px !important;
        }
        @media (max-width: 900px) {
            .hero-title {
                font-size: 24px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def save_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def init_session() -> None:
    defaults = {
        "ready": False,
        "finished": False,
        "question": None,
        "role": None,
        "plan": None,
        "memory": None,
        "pre_interview_brief": None,
        "final_profile": None,
        "report": None,
        "jd_structured": None,
        "resume_structured": None,
        "match_analysis": None,
        "config": None,
        "session_id": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_interview() -> None:
    for key in [
        "ready",
        "finished",
        "question",
        "role",
        "plan",
        "memory",
        "pre_interview_brief",
        "final_profile",
        "report",
        "jd_structured",
        "resume_structured",
        "match_analysis",
        "config",
        "session_id",
    ]:
        st.session_state.pop(key, None)
    init_session()


def as_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def tags(items: list[str], style: str = "") -> None:
    if not items:
        st.markdown('<span class="muted">暂无</span>', unsafe_allow_html=True)
        return
    html = "".join(f'<span class="tag {style}">{item}</span>' for item in items[:10])
    st.markdown(html, unsafe_allow_html=True)


def render_landing() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="hero-title">AI 模拟面试官 Agent</div>
          <p class="hero-subtitle">从 JD 与简历出发，自动完成角色设定、面试计划、多轮追问、结构化记忆和最终评估报告。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_landing_form() -> tuple[Any, str, str, bool]:
    st.markdown(
        """
        <div class="input-panel">
          <div class="input-title">面试资料</div>
          <div class="input-subtitle">上传候选人简历，粘贴岗位 JD；系统会自动生成面试官角色、面试计划和追问策略。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("interview_setup_form", clear_on_submit=False):
        resume_file = st.file_uploader("简历文件", type=["pdf", "docx"])
        jd_text_input = st.text_area(
            "JD 职位描述",
            height=220,
            placeholder="粘贴岗位职责、任职要求、核心技术栈和加分项。系统会据此拆解岗位能力，并生成面试官角色与考察路径。",
        )
        requirement_text = st.text_area(
            "面试官角色配置与流程要求",
            height=150,
            placeholder="可选。例如：你是一位严谨的后端技术面试官，重点考察项目真实性、MySQL、Redis、MQ 和工程落地能力，追问强度高一些。",
        )
        col_a, col_b = st.columns([1, 1])
        start = col_a.form_submit_button("开始面试", type="primary", use_container_width=True)
        reset = col_b.form_submit_button("重置", use_container_width=True)
        if reset:
            reset_interview()
            st.rerun()
        return resume_file, jd_text_input, requirement_text, start


def render_context_panel() -> None:
    role = st.session_state.role or {}
    brief = st.session_state.pre_interview_brief or {}
    match_analysis = st.session_state.match_analysis or {}
    plan = st.session_state.plan or {}
    memory: InterviewMemory | None = st.session_state.memory

    st.markdown(
        """
        <div class="topline">
          <div>
            <strong>面试上下文</strong><br>
            <span>角色、匹配、计划和记忆会随流程持续更新</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    tab_role, tab_match, tab_brief, tab_plan, tab_memory = st.tabs(["面试官", "匹配分析", "面试前简报", "面试计划", "记忆"])
    with tab_role:
        st.markdown(
            f"""
            <div class="subtle-box">
              <div class="subtle-box-title">{role.get('role', '技术面试官')}</div>
              <div class="subtle-box-body">{role.get('tone', '专业、直接、关注细节')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        tags(role.get("focus_areas", []), "tag-teal")
        with st.expander("查看角色 JSON"):
            st.json(role)
    with tab_match:
        m1, m2 = st.columns(2)
        m1.metric("匹配级别", match_analysis.get("match_level", "-"))
        m2.metric("推荐", match_analysis.get("recommendation", "待分析"))
        st.caption("匹配能力")
        tags(match_analysis.get("matched_capabilities", match_analysis.get("matched_skills", [])), "tag-teal")
        st.caption("待验证缺口")
        tags(match_analysis.get("possible_gaps", []), "tag-rose")
        st.caption("建议深挖")
        tags(match_analysis.get("interview_focus", match_analysis.get("recommended_focus", [])), "tag-amber")
        with st.expander("查看匹配 JSON"):
            st.json(match_analysis)
    with tab_brief:
        st.markdown(
            f"""
            <div class="subtle-box">
              <div class="subtle-box-title">面试前简报</div>
              <div class="subtle-box-body">{brief.get('brief_summary', '暂无面试前简报。')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("重点验证点")
        tags(brief.get("priority_verification_points", []), "tag-amber")
        with st.expander("查看简报 JSON"):
            st.json(brief)
    with tab_plan:
        stages = plan.get("stages", [])
        for stage in stages:
            st.markdown(
                f"""
                <div class="subtle-box">
                  <div class="subtle-box-title">{stage.get('name', stage.get('id'))}</div>
                  <div class="subtle-box-body">{stage.get('goal', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with st.expander("项目/实习深挖计划"):
            st.json(plan.get("experience_probe_plan", []))
        with st.expander("技能与场景计划"):
            st.json(plan.get("skill_scenario_plan", []))
        with st.expander("查看计划 JSON"):
            st.json(plan)
    with tab_memory:
        if memory:
            summary = memory.summary()
            m1, m2 = st.columns(2)
            m1.metric("当前轮次", summary["current_round"])
            m2.metric("已问问题", summary["asked_count"])
            st.caption("未闭环风险")
            tags(summary.get("open_risks", []), "tag-rose")
            with st.expander("查看记忆 JSON"):
                st.json(summary)
            store_overview = store.latest_overview()
            st.caption("SQLite 最近一次面试记忆")
            st.json(
                {
                    "db_path": store_overview["db_path"],
                    "turn_count": store_overview["turn_count"],
                    "direction_score_count": store_overview.get("direction_score_count", 0),
                    "status": (store_overview.get("session") or {}).get("status"),
                    "has_profile": store_overview["has_profile"],
                }
            )
        else:
            st.info("面试开始后会生成记忆。")

    render_runtime_status()


def render_runtime_status() -> None:
    status = llm.status()
    avatar_config = load_xingyun_avatar_config()
    tts_config = load_browser_tts_config()
    with st.expander("运行状态"):
        st.json(
            {
                "llm_available": status.available,
                "model": status.model,
                "base_url": status.base_url,
                "last_error": status.last_error,
                "fallback_mode": not status.available or bool(status.last_error),
                "xingyun_avatar_enabled": avatar_config.enabled,
                "xingyun_avatar_ready": avatar_config.ready,
                "browser_tts_enabled": tts_config.enabled,
            }
        )


def render_interview() -> None:
    memory: InterviewMemory = st.session_state.memory
    question = st.session_state.question

    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-title">第 {memory.current_round} 轮 · {memory.current_stage_name}</div>
          <p class="hero-subtitle">系统会基于当前阶段、历史问答和未闭环风险生成下一题；提交后只记录观察，不做单题打分。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("当前阶段", memory.current_stage_name)
    c2.metric("连续追问", memory.consecutive_followups)
    c3.metric("未闭环风险", len(memory.open_risks))

    st.markdown(
        f"""
        <div class="question">
          <div class="question-label">Current Question</div>
          {question["question"]}
        </div>
        <div class="question-meta">
          <span class="tag tag-teal">考察点：{question.get('focus_area', '当前阶段')}</span>
          <span class="tag">类型：{question.get('question_type', 'new_topic')}</span>
          <span class="tag tag-amber">预期信号：{question.get('expected_signal', '观察回答是否具体、有证据')}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if question.get("reason"):
        st.caption(f"出题依据：{question.get('reason')}")

    tts_config = load_browser_tts_config()
    if tts_config.enabled:
        components.html(
            build_browser_tts_html(question["question"], tts_config),
            height=tts_config.height,
        )

    avatar_config = load_xingyun_avatar_config()
    if avatar_config.enabled:
        if avatar_config.ready:
            components.html(
                build_xingyun_avatar_html(question["question"], avatar_config),
                height=avatar_config.height,
            )
        else:
            st.warning("已启用星云数字人，但缺少 XINGYUN_APP_ID 或 XINGYUN_APP_SECRET。")

    answer = st.text_area("你的回答", height=210, key=f"answer_{memory.current_round}")
    submit = st.button("提交回答", type="primary", use_container_width=True)

    if submit:
        if not answer.strip():
            st.warning("请先输入回答。")
            return
        with st.spinner("正在评估回答并决定下一步..."):
            evaluation = evaluate_answer(
                llm,
                question,
                answer,
                st.session_state.plan,
                memory,
                st.session_state.resume_structured,
                st.session_state.jd_structured,
            )
            memory.record_turn(question, answer, evaluation)
            if st.session_state.session_id:
                store.add_turn(st.session_state.session_id, memory.conversation[-1].model_dump())
            _, direction_score = flow_controller.apply(
                memory,
                llm=llm,
                plan=st.session_state.plan,
                jd=st.session_state.jd_structured,
                resume=st.session_state.resume_structured,
            )
            if direction_score and st.session_state.session_id:
                store.add_direction_score(st.session_state.session_id, direction_score)
            if memory.should_finish():
                final_profile = build_final_profile(
                    llm,
                    st.session_state.pre_interview_brief,
                    st.session_state.plan,
                    memory,
                )
                report = build_report(
                    llm,
                    st.session_state.role,
                    st.session_state.plan,
                    memory,
                    final_profile,
                )
                st.session_state.final_profile = final_profile
                st.session_state.report = report
                st.session_state.finished = True
                if st.session_state.session_id:
                    store.finish_session(
                        st.session_state.session_id,
                        final_profile=final_profile,
                        report=report,
                    )
            else:
                st.session_state.question = generate_next_question(
                    llm,
                    st.session_state.role,
                    st.session_state.plan,
                    memory,
                    st.session_state.resume_structured,
                    st.session_state.jd_structured,
                )
        st.rerun()


def render_report() -> None:
    final_profile = st.session_state.final_profile or {}
    report = st.session_state.report or {}

    st.markdown(
        """
        <div class="hero">
          <div class="hero-title">面试评估报告</div>
          <p class="hero-subtitle">基于完整问答记忆生成，包含候选人最终画像、风险证据和下一轮建议。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("问答轮次", len(st.session_state.memory.conversation))
    c2.metric("记录风险", len(st.session_state.memory.open_risks))
    c3.metric("证据链", len(report.get("evidence_chain", [])))

    tab_summary, tab_match, tab_profile, tab_scores, tab_evidence, tab_json = st.tabs(["结论", "匹配与沟通", "最终画像", "方向评分", "证据链", "JSON"])
    with tab_summary:
        st.markdown(report.get("readable_report", "暂无可读报告。"))
        st.download_button(
            "下载人读版报告 Markdown",
            data=report.get("readable_report", ""),
            file_name="interview_report.md",
            mime="text/markdown",
        )
    with tab_match:
        st.markdown("#### 岗位匹配度")
        job_match = report.get("job_match", {}) or {}
        st.write(job_match.get("summary", "暂无岗位匹配摘要。"))
        tags(job_match.get("validated_strengths", []), "tag-teal")
        tags(job_match.get("remaining_gaps", []), "tag-rose")
        st.markdown("#### 沟通能力")
        communication = report.get("communication", {}) or {}
        st.write(communication.get("summary", "暂无沟通摘要。"))
        tags(communication.get("observations", []), "tag-teal")
        tags(communication.get("risks", []), "tag-rose")
    with tab_profile:
        st.json(final_profile)
    with tab_scores:
        scores = report.get("direction_scores", [])
        if scores:
            for score in scores:
                st.markdown(
                    f"#### {score.get('direction', '未命名方向')}：{score.get('level_label', '未验证')} ({score.get('verification_level', '-')}/4)"
                )
                if score.get("judgement"):
                    st.write(score["judgement"])
                if score.get("evidence"):
                    st.caption("证据")
                    tags(score.get("evidence", []), "tag-teal")
                if score.get("missing_points"):
                    st.caption("缺失点")
                    tags(score.get("missing_points", []), "tag-rose")
                if score.get("suggestion"):
                    st.info(score["suggestion"])
        else:
            st.caption("暂无方向评分。")
    with tab_evidence:
        st.json(report.get("evidence_chain", []))
    with tab_json:
        package = {
            "report": report,
            "final_profile": final_profile,
            "memory": st.session_state.memory.model_dump(),
            "match_analysis": st.session_state.match_analysis,
            "pre_interview_brief": st.session_state.pre_interview_brief,
            "role": st.session_state.role,
            "plan": st.session_state.plan,
        }
        st.json(package)
        st.download_button(
            "下载完整评估包 JSON",
            data=as_json(package),
            file_name="interview_report.json",
            mime="application/json",
        )


render_css()
init_session()
llm = LLMClient()
store = InterviewStore()
flow_controller = InterviewFlowController()

def start_interview(resume_file: Any, jd_text_input: str, requirement_text: str) -> None:
    if not resume_file:
        st.error("请先上传一份简历。")
        return
    if not jd_text_input.strip():
        st.error("请填写 JD 职位描述。")
        return

    with st.spinner("正在解析资料并生成面试计划..."):
        resume_doc = load_document(save_upload(resume_file))
        jd_text = jd_text_input.strip()

        config = build_interview_config(llm, requirement_text)
        jd_structured = structure_jd(llm, jd_text)
        resume_structured = structure_resume(llm, resume_doc.text)
        match_analysis = build_match_analysis(llm, jd_structured, resume_structured)
        role = build_interviewer_role(llm, jd_structured, config)
        pre_interview_brief = build_pre_interview_brief(llm, jd_structured, resume_structured, config, match_analysis)
        plan = build_interview_plan(
            llm,
            jd_structured,
            resume_structured,
            pre_interview_brief,
            role,
            config,
            match_analysis,
        )
        memory = InterviewMemory.from_plan(plan)
        question = generate_next_question(llm, role, plan, memory, resume_structured, jd_structured)
        session_id = store.start_latest_session(
            jd_text=jd_text,
            resume_text=resume_doc.text,
            jd_structured=jd_structured,
            resume_structured=resume_structured,
            match_analysis=match_analysis,
            role=role,
            plan=plan,
            pre_interview_brief=pre_interview_brief,
        )

        st.session_state.config = config
        st.session_state.jd_structured = jd_structured
        st.session_state.resume_structured = resume_structured
        st.session_state.match_analysis = match_analysis
        st.session_state.role = role
        st.session_state.pre_interview_brief = pre_interview_brief
        st.session_state.plan = plan
        st.session_state.memory = memory
        st.session_state.question = question
        st.session_state.session_id = session_id
        st.session_state.ready = True
        st.session_state.finished = False
    st.rerun()

if not st.session_state.ready:
    render_landing()
    resume_file, jd_text_input, requirement_text, start = render_landing_form()
    if start:
        start_interview(resume_file, jd_text_input, requirement_text)
else:
    main_col, side_col = st.columns([1.65, 1], gap="large")
    with main_col:
        if st.session_state.finished:
            render_report()
        else:
            render_interview()
    with side_col:
        render_context_panel()
