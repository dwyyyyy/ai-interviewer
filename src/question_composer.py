from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import InterviewMemory


def compose_question(
    llm: LLMClient,
    role: dict,
    plan: dict,
    memory: InterviewMemory,
    resume: dict,
    jd: dict,
    probe: dict,
    retrieved_questions: list[dict],
) -> dict:
    fallback = _fallback_compose(memory, probe, retrieved_questions)
    if not llm.available:
        return fallback

    prompt = f"""
你是一名专业面试问题设计专家，负责将考察方向、题库候选题、JD 场景和候选人经历组合成最终面试问题。

任务目标：
1. 每次只生成一个问题，问题要具体、自然、可追问。
2. 问题必须结合候选人的具体经历或作品，不要生成通用八股题。
3. 问题要能验证至少一个明确能力点，例如个人贡献、业务理解、方案设计、指标复盘、工具使用深度或落地可行性。
4. 如果当前是追问，应围绕上一轮缺口继续深入，而不是开启新话题。
5. expected_signal 要描述优秀回答应该包含哪些证据。
6. probe_direction 是 Planner 已确定的大方向，不要改变大方向，只能在该方向下细化具体问法。
7. 如果考察方向包含 source_experience，问题必须围绕该项目/实习的具体内容展开；如果 source_detail 不为空，必须使用其中的项目事实。
8. 题库候选题是 Top 10 相关题，请选择最贴近当前大方向和项目内容的一题作为参考，再融合成一个最终问题；不要照抄题库，不要一次问多个问题。

面试官角色：{role}
当前阶段：{memory.current_stage}
面试计划：{plan}
记忆摘要：{memory.summary()}
最近问答：{memory.recent_turns()}
考察方向：{probe}
题库候选题 Top 10：{retrieved_questions}
简历结构：{resume}
JD结构：{jd}

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 输出字段：question, question_type, focus_area, reason, expected_signal, retrieved_question_ids。
"""
    data = extract_json(llm.complete("你是专业的招聘面试问题设计器。", prompt), fallback)
    return _normalize_question(data, fallback, probe, retrieved_questions)


def _fallback_compose(memory: InterviewMemory, probe: dict, retrieved_questions: list[dict]) -> dict:
    top = retrieved_questions[0] if retrieved_questions else {}
    topic = top.get("topic") or probe.get("target_capability") or memory.current_stage_name
    template = top.get("question_template") or f"请结合你的项目经历说明 {probe.get('probe_direction', '该方向')}。"
    project_hint = _project_hint_from_probe(probe)
    detail = probe.get("source_detail")
    detail_hint = f" 项目背景参考：{detail[:180]}。" if detail else ""
    question = f"{template} 请结合{project_hint}，围绕「{probe.get('probe_direction', topic)}」说明你的个人贡献、关键实现和遇到的问题。{detail_hint}"
    if memory.consecutive_followups > 0:
        question = f"围绕刚才的回答，继续在「{probe.get('probe_direction', topic)}」这个方向上追问。请结合{project_hint}补充关键细节、取舍原因和可量化结果。{detail_hint}"
    return {
        "question": question,
        "question_type": "retrieval_augmented_follow_up" if memory.consecutive_followups > 0 else "retrieval_augmented",
        "focus_area": probe.get("probe_direction", topic),
        "reason": probe.get("reason", "基于题库检索和当前面试阶段生成。"),
        "expected_signal": "候选人好的回答应结合真实项目，覆盖个人贡献、技术方案、取舍、指标和风险处理。",
        "retrieved_question_ids": [item.get("id") for item in retrieved_questions if item.get("id")],
    }


def _project_hint_from_probe(probe: dict) -> str:
    if probe.get("source_experience"):
        return f"「{probe['source_experience']}」这段经历"
    if probe.get("scenario_context"):
        return f"「{probe['scenario_context']}」这个技能或场景"
    direction = str(probe.get("probe_direction", "你简历中的相关项目"))
    if "Agent" in direction or "记忆" in direction:
        return "你简历中的 Agent Harness 或相关 Agent 项目"
    if "MCP" in direction:
        return "你实习中的 MCP 工具开发经历"
    if "RAG" in direction or "召回" in direction:
        return "你简历中的 RAG 或知识召回经历"
    return "你简历中的一个具体项目"


def _normalize_question(data: object, fallback: dict, probe: dict, retrieved_questions: list[dict]) -> dict:
    if not isinstance(data, dict):
        data = fallback.copy()
    result = fallback.copy()
    for key, value in data.items():
        if value not in (None, "", []):
            result[key] = value

    # The scoring unit is the Planner direction. Question generation may use a
    # retrieved topic as reference, but focus_area must remain the stable big
    # direction so later turns can be grouped and scored correctly.
    result["focus_area"] = probe.get("probe_direction") or result.get("focus_area") or fallback.get("focus_area")
    if not result.get("retrieved_question_ids"):
        result["retrieved_question_ids"] = [item.get("id") for item in retrieved_questions if item.get("id")]
    return result
