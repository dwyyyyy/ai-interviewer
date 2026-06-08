from __future__ import annotations

from copy import deepcopy

from src.json_utils import extract_json
from src.llm_client import LLMClient


def build_interview_plan(
    llm: LLMClient,
    jd: dict,
    resume: dict,
    pre_interview_brief: dict,
    role: dict,
    config: dict,
    match_analysis: dict,
) -> dict:
    flow = _adaptive_interview_flow(config, match_analysis)
    stages = flow["stages"]
    key_experiences = match_analysis.get(
        "key_experiences_to_probe",
        resume.get("projects", [])[:3] + resume.get("internships", [])[:2],
    )
    matched_skills = match_analysis.get("matched_skills", pre_interview_brief.get("matched_skills", []))
    fallback = {
        "interview_goal": "验证候选人与岗位的匹配度、项目真实性、技术深度和工程落地能力。",
        "demo_rounds": flow["demo_rounds"],
        "target_rounds": flow["target_rounds"],
        "stages": stages,
        "key_experiences_to_probe": key_experiences,
        "experience_probe_plan": _build_experience_probe_plan(key_experiences, match_analysis),
        "matched_tech_stack": matched_skills,
        "skill_scenario_plan": _build_skill_scenario_plan(jd, matched_skills, match_analysis),
        "must_verify_risks": match_analysis.get("technical_risks", match_analysis.get("risks", pre_interview_brief.get("priority_verification_points", []))),
        "recommended_focus": match_analysis.get("interview_focus", match_analysis.get("recommended_focus", [])),
    }
    if not llm.available:
        return fallback

    prompt = f"""
你是一名招聘面试方案设计专家，负责将岗位要求、面试前简报和匹配分析转化为可执行的多轮面试计划。

任务目标：
1. 保留默认流程阶段，不要删除或重排核心阶段，但可以补充每个阶段的验证重点。
2. 面试计划要围绕 match_analysis 中的匹配点、缺口、风险和重点经历展开。
3. experience_probe_plan 是简历深挖阶段的考察地图：针对每个项目/实习沉淀 2-3 个大方向，每个方向包含 objective 和 evidence_to_seek。
4. skill_scenario_plan 是技能与场景题阶段的考察地图：针对 JD 与简历匹配技能，沉淀可迁移到业务场景的问题方向。
5. key_experiences_to_probe 应优先选择与岗位能力最相关、最能验证个人贡献和真实性的经历。
6. must_verify_risks 应表述为面试中需要验证的问题，不要做最终定性。
7. recommended_focus 应能直接指导后续提问，例如平台迁移能力、AI 内容 SOP、指标复盘、Agent 原型落地。
8. target_rounds 是建议轮次，不是固定轮次；后续 Interview Memory 可根据回答充分度提前结束或追问延展。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 只能输出字段：interview_goal, demo_rounds, target_rounds, stages, key_experiences_to_probe, experience_probe_plan, matched_tech_stack, skill_scenario_plan, must_verify_risks, recommended_focus。

JD：{jd}
简历：{resume}
匹配分析：{match_analysis}
面试前简报：{pre_interview_brief}
面试官：{role}
流程配置：{flow}

字段：interview_goal, demo_rounds, target_rounds, stages, key_experiences_to_probe,
experience_probe_plan, matched_tech_stack, skill_scenario_plan, must_verify_risks, recommended_focus。
"""
    data = extract_json(llm.complete("你是专业的招聘面试方案设计器。", prompt), fallback)
    return _merge_plan_defaults(fallback, data)


def _adaptive_interview_flow(config: dict, match_analysis: dict) -> dict:
    flow = deepcopy(config["interview_flow"])
    stages = deepcopy(flow.get("stages", []))
    base_rounds = int(flow.get("target_rounds") or flow.get("demo_rounds") or 6)
    gap_count = len(match_analysis.get("possible_gaps", []))
    risk_count = len(match_analysis.get("technical_risks", match_analysis.get("risks", [])))
    probe_count = len(match_analysis.get("key_experiences_to_probe", []))

    if gap_count + risk_count >= 5 or probe_count >= 4:
        target_rounds = max(base_rounds, 8)
    elif gap_count + risk_count <= 1 and probe_count <= 1:
        target_rounds = min(base_rounds, 5)
    else:
        target_rounds = base_rounds
    target_rounds = max(4, min(target_rounds, 10))

    remaining = max(target_rounds - 2, 2)
    resume_rounds = max(1, round(remaining * 0.65))
    scenario_rounds = max(1, remaining - resume_rounds)

    for stage in stages:
        stage_id = stage.get("id")
        if stage_id == "self_intro":
            stage["demo_rounds"] = 1
        elif stage_id == "resume_deep_dive":
            stage["demo_rounds"] = resume_rounds
        elif stage_id == "tech_stack_scenario":
            stage["demo_rounds"] = scenario_rounds
        elif stage_id == "candidate_questions":
            stage["demo_rounds"] = 1

    flow["stages"] = stages
    flow["target_rounds"] = target_rounds
    flow["demo_rounds"] = target_rounds
    return flow


def _build_experience_probe_plan(experiences: list[dict], match_analysis: dict) -> list[dict]:
    risks = match_analysis.get("technical_risks", match_analysis.get("risks", []))
    focus = match_analysis.get("interview_focus", match_analysis.get("recommended_focus", []))
    result = []
    for exp in experiences[:5]:
        name = str(exp.get("name") or exp.get("description") or "相关经历")[:80]
        keywords = exp.get("matched_keywords", []) or []
        directions = [
            {
                "direction": "个人贡献与真实性",
                "objective": f"确认候选人在「{name}」中的真实职责、决策边界和可独立复现部分。",
                "evidence_to_seek": ["本人负责模块", "关键决策", "协作边界", "可复盘细节"],
            },
            {
                "direction": "方法与执行链路",
                "objective": f"拆解「{name}」从目标、方案、执行到复盘的完整链路。",
                "evidence_to_seek": ["流程步骤", "工具/平台", "关键取舍", "异常处理"],
            },
            {
                "direction": "结果指标与复盘",
                "objective": f"验证「{name}」的指标口径、业务结果和可迁移经验。",
                "evidence_to_seek": ["指标基准", "结果变化", "归因逻辑", "复盘改进"],
            },
        ]
        if keywords:
            directions[1]["objective"] += f" 重点覆盖：{', '.join(map(str, keywords[:5]))}。"
        if risks or focus:
            directions[2]["objective"] += f" 结合待验证点：{', '.join(map(str, (risks + focus)[:3]))}。"
        result.append(
            {
                "experience_name": name,
                "experience_type": exp.get("type", "experience"),
                "experience_summary": str(exp.get("description") or exp.get("raw") or exp.get("match_reason") or "")[:800],
                "claimed_contribution": str(exp.get("claimed_contribution") or "")[:400],
                "match_reason": exp.get("match_reason", ""),
                "matched_keywords": keywords,
                "directions": directions,
            }
        )
    return result


def _build_skill_scenario_plan(jd: dict, skills: list[str], match_analysis: dict) -> list[dict]:
    business_context = jd.get("business_context", "")
    gaps = match_analysis.get("possible_gaps", [])
    focus = match_analysis.get("interview_focus", match_analysis.get("recommended_focus", []))
    plan = []
    for skill in skills[:6]:
        plan.append(
            {
                "skill": skill,
                "scenario_context": business_context,
                "directions": [
                    {
                        "direction": "场景迁移",
                        "objective": f"验证候选人能否把 {skill} 迁移到 {business_context or '目标岗位业务场景'}。",
                        "evidence_to_seek": ["场景理解", "方案设计", "落地步骤", "边界条件"],
                    },
                    {
                        "direction": "工具/方法深度",
                        "objective": f"验证候选人对 {skill} 的真实使用深度，而不是停留在概念或简单调用。",
                        "evidence_to_seek": ["工具链", "关键参数/策略", "质量控制", "效果评估"],
                    },
                    {
                        "direction": "风险与复盘",
                        "objective": f"验证候选人使用 {skill} 时如何处理失败、成本、质量和复盘优化。",
                        "evidence_to_seek": ["失败案例", "监控指标", "优化动作", "复盘沉淀"],
                    },
                ],
                "related_gaps": gaps[:3],
                "related_focus": focus[:3],
            }
        )
    return plan


def _merge_plan_defaults(fallback: dict, data: object) -> dict:
    if not isinstance(data, dict):
        return fallback
    merged = fallback.copy()
    for key, value in data.items():
        if value not in (None, "", []):
            merged[key] = value
    return merged
