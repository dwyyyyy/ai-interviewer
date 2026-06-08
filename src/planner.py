from __future__ import annotations

from copy import deepcopy

from src.json_utils import extract_json
from src.llm_client import LLMClient


def build_self_intro_plan(config: dict) -> dict:
    stages = deepcopy(config["interview_flow"].get("stages", []))
    intro_stage = next(
        (stage for stage in stages if stage.get("id") == "self_intro"),
        {
            "id": "self_intro",
            "name": "3分钟自我介绍",
            "duration_minutes": 3,
            "demo_rounds": 1,
            "goal": "观察候选人的表达结构、职业主线和岗位相关经历。",
        },
    )
    intro_stage = deepcopy(intro_stage)
    intro_stage["demo_rounds"] = 1
    return {
        "interview_goal": "先完成候选人自我介绍，再基于 JD、简历、匹配分析和自我介绍生成后续面试计划。",
        "demo_rounds": 1,
        "target_rounds": 1,
        "stages": [intro_stage],
        "key_experiences_to_probe": [],
        "experience_probe_plan": [],
        "matched_tech_stack": [],
        "skill_scenario_plan": [],
        "must_verify_risks": [],
        "recommended_focus": [],
        "plan_status": "waiting_for_self_intro",
    }


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


def refine_plan_with_self_intro(
    llm: LLMClient,
    plan: dict,
    *,
    self_intro_answer: str,
    jd: dict,
    resume: dict,
    match_analysis: dict,
) -> dict:
    refined = deepcopy(plan)
    intro_summary = self_intro_answer.strip()[:1200]
    refined["self_intro_summary"] = intro_summary
    refined["self_intro_used_for_planning"] = True

    refined["experience_probe_plan"] = _prioritize_intro_experiences(
        refined.get("experience_probe_plan", []),
        intro_summary,
    )
    refined["skill_scenario_plan"] = _prioritize_intro_skills(
        refined.get("skill_scenario_plan", []),
        intro_summary,
    )
    intro_keywords = _extract_intro_keywords(intro_summary)
    if intro_keywords:
        recommended = list(refined.get("recommended_focus", []))
        refined["recommended_focus"] = list(dict.fromkeys(intro_keywords + recommended))

    if not llm.available:
        return refined

    prompt = f"""
你是一名面试计划校准专家。候选人刚完成自我介绍，请基于这段自述微调后续面试计划。

目标：
1. 不改变面试阶段结构，不重新设计整场面试。
2. 将候选人主动强调的项目、实习、技能、成果或业务场景，加入后续深挖优先级。
3. 如果自我介绍中出现简历里未充分展开但与 JD 高相关的经历，应加入 key_experiences_to_probe 或 recommended_focus。
4. 保留原 plan 中已有的重要风险和 JD 核心要求，不要只跟着候选人自述走。
5. experience_probe_plan 仍然要按“大方向”组织，每个经历保留 2-3 个方向。
6. skill_scenario_plan 仍然围绕技能和业务场景，不要生成具体小问题。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 只能输出字段：key_experiences_to_probe, experience_probe_plan, matched_tech_stack, skill_scenario_plan, must_verify_risks, recommended_focus, self_intro_summary, self_intro_planning_notes。

原计划：{plan}
自我介绍：{self_intro_answer}
JD：{jd}
简历：{resume}
匹配分析：{match_analysis}
"""
    data = extract_json(llm.complete("你是专业的面试计划校准器。", prompt), {})
    if not isinstance(data, dict):
        return refined
    for key in [
        "key_experiences_to_probe",
        "experience_probe_plan",
        "matched_tech_stack",
        "skill_scenario_plan",
        "must_verify_risks",
        "recommended_focus",
        "self_intro_summary",
        "self_intro_planning_notes",
    ]:
        if data.get(key) not in (None, "", []):
            refined[key] = data[key]
    refined["self_intro_used_for_planning"] = True
    return refined


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

    flow["stages"] = stages
    flow["target_rounds"] = target_rounds
    flow["demo_rounds"] = target_rounds
    return flow


def _prioritize_intro_experiences(experience_plan: list[dict], intro: str) -> list[dict]:
    if not isinstance(experience_plan, list) or not intro:
        return experience_plan
    intro_lower = intro.lower()

    def score(item: dict) -> int:
        text = " ".join(
            str(item.get(key, ""))
            for key in ["experience_name", "experience_summary", "claimed_contribution", "match_reason"]
        ).lower()
        return sum(1 for token in _tokens_for_match(text) if token and token in intro_lower)

    return sorted(experience_plan, key=score, reverse=True)


def _prioritize_intro_skills(skill_plan: list[dict], intro: str) -> list[dict]:
    if not isinstance(skill_plan, list) or not intro:
        return skill_plan
    intro_lower = intro.lower()
    return sorted(
        skill_plan,
        key=lambda item: int(str(item.get("skill", "")).lower() in intro_lower),
        reverse=True,
    )


def _extract_intro_keywords(intro: str) -> list[str]:
    keywords = []
    keyword_map = {
        "自我介绍提到的重点项目": ["项目", "负责", "参与", "主导"],
        "自我介绍提到的业务结果": ["提升", "增长", "转化", "指标", "数据"],
        "自我介绍提到的 AI 工具/Agent 经验": ["agent", "rag", "prompt", "chatgpt", "大模型", "工作流"],
        "自我介绍提到的个人贡献边界": ["我负责", "我主要", "个人贡献", "独立"],
    }
    intro_lower = intro.lower()
    for label, words in keyword_map.items():
        if any(word.lower() in intro_lower for word in words):
            keywords.append(label)
    return keywords


def _tokens_for_match(text: str) -> list[str]:
    return [
        token.strip("，。；;,.()（）[]【】 ")
        for token in text.replace("/", " ").replace("|", " ").split()
        if len(token.strip()) >= 2
    ]


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
