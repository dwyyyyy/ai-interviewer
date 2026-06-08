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
        "stages": [intro_stage],
        "key_experiences_to_probe": [],
        "experience_probe_plan": [],
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
    fallback = {
        "interview_goal": "验证候选人与岗位的匹配度、项目真实性、技术深度和工程落地能力。",
        "demo_rounds": flow["demo_rounds"],
        "target_rounds": flow["target_rounds"],
        "stages": stages,
        "key_experiences_to_probe": key_experiences,
        "experience_probe_plan": _build_experience_probe_plan(key_experiences, match_analysis),
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
4. 不再单独生成技能或场景题阶段；岗位技能要融入项目/实习深挖方向里验证。
5. key_experiences_to_probe 应优先选择与岗位能力最相关、最能验证个人贡献和真实性的经历。
6. must_verify_risks 应表述为面试中需要验证的问题，不要做最终定性。
7. recommended_focus 应能直接指导后续提问，例如平台迁移能力、AI 内容 SOP、指标复盘、Agent 原型落地。
8. 不要生成固定总轮次；后续轮次由 experience_probe_plan 中的大方向数量决定。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 只能输出字段：interview_goal, stages, key_experiences_to_probe, experience_probe_plan, must_verify_risks, recommended_focus。

JD：{jd}
简历：{resume}
匹配分析：{match_analysis}
面试前简报：{pre_interview_brief}
面试官：{role}
流程配置：{flow}

字段：interview_goal, stages, key_experiences_to_probe,
experience_probe_plan, must_verify_risks, recommended_focus。
"""
    data = extract_json(llm.complete("你是专业的招聘面试方案设计器。", prompt), fallback)
    return _sync_stage_rounds_to_plan(_merge_plan_defaults(fallback, data))


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
2. 将候选人主动强调的项目、实习、技能、成果或业务场景，加入项目/实习深挖优先级。
3. 如果自我介绍中出现简历里未充分展开但与 JD 高相关的经历，应加入 key_experiences_to_probe 或 recommended_focus。
4. 保留原 plan 中已有的重要风险和 JD 核心要求，不要只跟着候选人自述走。
5. experience_probe_plan 仍然要按“大方向”组织，每个经历保留 2-3 个方向。
6. 不要生成独立技能题计划；技能和业务场景只作为项目/实习深挖方向中的验证重点。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 只能输出字段：key_experiences_to_probe, experience_probe_plan, must_verify_risks, recommended_focus, self_intro_summary, self_intro_planning_notes。

原计划：{plan}
自我介绍：{self_intro_answer}
JD：{jd}
简历：{resume}
匹配分析：{match_analysis}
"""
    data = extract_json(llm.complete("你是专业的面试计划校准器。", prompt), {})
    if not isinstance(data, dict):
        return _sync_stage_rounds_to_plan(refined)
    for key in [
        "key_experiences_to_probe",
        "experience_probe_plan",
        "must_verify_risks",
        "recommended_focus",
        "self_intro_summary",
        "self_intro_planning_notes",
    ]:
        if data.get(key) not in (None, "", []):
            refined[key] = data[key]
    refined["self_intro_used_for_planning"] = True
    return _sync_stage_rounds_to_plan(refined)


def _adaptive_interview_flow(config: dict, match_analysis: dict) -> dict:
    flow = deepcopy(config["interview_flow"])
    stages = deepcopy(flow.get("stages", []))

    for stage in stages:
        stage_id = stage.get("id")
        if stage_id == "self_intro":
            stage["demo_rounds"] = 1
        elif stage_id == "resume_deep_dive":
            stage["demo_rounds"] = 1

    flow["stages"] = stages
    flow["target_rounds"] = sum(int(stage.get("demo_rounds", 1)) for stage in stages)
    flow["demo_rounds"] = flow["target_rounds"]
    return flow


def _sync_stage_rounds_to_plan(plan: dict) -> dict:
    synced = deepcopy(plan)
    stages = deepcopy(synced.get("stages", []))
    experience_rounds = _count_experience_directions(synced)

    for stage in stages:
        stage_id = stage.get("id")
        if stage_id == "self_intro":
            stage["demo_rounds"] = 1
        elif stage_id == "resume_deep_dive":
            stage["demo_rounds"] = max(1, experience_rounds)

    synced["stages"] = stages
    total_rounds = sum(int(stage.get("demo_rounds", 1)) for stage in stages)
    synced["target_rounds"] = total_rounds
    synced["demo_rounds"] = total_rounds
    synced["round_policy"] = "plan_driven"
    return synced


def _count_experience_directions(plan: dict) -> int:
    total = 0
    for item in plan.get("experience_probe_plan", []) or []:
        directions = item.get("directions", []) if isinstance(item, dict) else []
        total += len(directions) if directions else 1
    if total:
        return total
    return len(plan.get("key_experiences_to_probe", []) or [])

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


def _merge_plan_defaults(fallback: dict, data: object) -> dict:
    if not isinstance(data, dict):
        return fallback
    merged = fallback.copy()
    for key, value in data.items():
        if value not in (None, "", []):
            merged[key] = value
    return merged
