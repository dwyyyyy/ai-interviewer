from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import InterviewMemory


def plan_probe_direction(
    llm: LLMClient,
    plan: dict,
    memory: InterviewMemory,
    resume: dict,
    jd: dict,
) -> dict:
    fallback = _fallback_probe(plan, memory)
    if not llm.available:
        return fallback
    prompt = f"""
你是一名面试考察方向规划专家，负责根据当前阶段、面试计划和历史问答选择下一题最值得验证的能力点。

任务目标：
1. 简历深挖阶段优先从 plan.experience_probe_plan 中选择当前大方向；一个方向信号足够后再进入下一个方向。
2. 技能与场景题阶段优先从 plan.skill_scenario_plan 中选择当前大方向。
3. 如果 consecutive_followups > 0，说明上一轮还没问透，应继续围绕上一轮 focus_area 追问，不要切换大方向。
4. draft_question 是内部草稿问题，只用于检索题库，不直接展示给候选人。
5. query 用于题库检索，应包含核心业务词、能力词、经历名称和工具/平台词。

当前阶段：{memory.current_stage}
面试计划：{plan}
记忆摘要：{memory.summary()}
最近问答：{memory.recent_turns()}
简历结构：{resume}
JD结构：{jd}

输出字段：
probe_direction, target_capability, difficulty, reason, draft_question, query, source_experience, source_detail, scenario_context。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
"""
    return extract_json(llm.complete("你是专业的面试考察方向规划器。", prompt), fallback)


def _fallback_probe(plan: dict, memory: InterviewMemory) -> dict:
    stage_id = memory.current_stage_id
    if memory.consecutive_followups > 0 and memory.conversation:
        last = memory.conversation[-1]
        focus = last.focus_area
        return {
            "probe_direction": focus,
            "target_capability": focus,
            "difficulty": "middle",
            "reason": "上一轮回答尚未闭环，继续围绕同一考察方向追问。",
            "draft_question": f"请继续追问 {focus}，要求候选人补充个人贡献、关键证据、指标口径和复盘细节。",
            "query": f"{focus} follow up evidence contribution metrics review",
            "source_experience": "",
            "source_detail": "",
            "scenario_context": "",
        }
    if stage_id == "resume_deep_dive":
        item = _select_experience_direction(plan.get("experience_probe_plan", []), memory.stage_round_index)
        focus = item.get("direction", "项目真实性与个人贡献")
        source = item.get("experience_name", "")
        objective = item.get("objective", "")
        query = f"{source} {focus} {objective} contribution evidence metrics review"
    elif stage_id == "tech_stack_scenario":
        item = _select_skill_direction(plan.get("skill_scenario_plan", []), memory.stage_round_index)
        focus = item.get("direction", item.get("skill", "场景迁移能力"))
        source = item.get("skill", "")
        objective = item.get("objective", "")
        query = f"{source} {focus} {objective} business scenario evaluation"
    else:
        focus = memory.current_stage_name
        source = ""
        objective = ""
        query = focus
    return {
        "probe_direction": focus,
        "target_capability": focus,
        "difficulty": "middle",
        "reason": "基于当前阶段和面试计划中的考察地图生成。",
        "draft_question": f"请结合{source or '候选人的相关经历'}，追问 {focus}。{objective}",
        "query": query,
        "source_experience": source if stage_id == "resume_deep_dive" else "",
        "source_detail": item.get("experience_summary", "") if stage_id == "resume_deep_dive" else "",
        "scenario_context": source if stage_id == "tech_stack_scenario" else "",
    }


def _select_experience_direction(plan_items: list[dict], index: int) -> dict:
    flattened = []
    for item in plan_items:
        for direction in item.get("directions", [])[:3]:
            flattened.append(
                {
                    "experience_name": item.get("experience_name", ""),
                    "experience_summary": item.get("experience_summary", ""),
                    "direction": direction.get("direction", ""),
                    "objective": direction.get("objective", ""),
                    "evidence_to_seek": direction.get("evidence_to_seek", []),
                }
            )
    if not flattened:
        return {}
    return flattened[min(index, len(flattened) - 1)]


def _select_skill_direction(plan_items: list[dict], index: int) -> dict:
    flattened = []
    for item in plan_items:
        for direction in item.get("directions", [])[:3]:
            flattened.append(
                {
                    "skill": item.get("skill", ""),
                    "direction": direction.get("direction", ""),
                    "objective": direction.get("objective", ""),
                    "evidence_to_seek": direction.get("evidence_to_seek", []),
                }
            )
    if not flattened:
        return {}
    return flattened[min(index, len(flattened) - 1)]
