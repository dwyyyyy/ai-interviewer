from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.json_utils import extract_json
from src.llm_client import LLMClient


def build_match_analysis(llm: LLMClient, jd: dict, resume: dict) -> dict:
    fallback = _rule_based_match(jd, resume)
    if not llm.available:
        return fallback

    prompt = f"""
你是一名资深招聘面试前分析专家，负责基于结构化 JD 与结构化简历生成 Match Review，用于指导后续面试官 Agent 的提问策略。

分析目标：
1. 判断候选人与岗位的能力相关性，而不是给候选人排序或做最终录用决定。
2. 将 JD 的必备能力、业务场景和核心职责，与简历中的技能、经历、项目和成果进行语义对齐。
3. 明确哪些能力已经有简历证据支撑，哪些要求仍未充分体现，哪些经历最值得面试深挖。
4. 将风险表述为“待验证假设”，例如个人贡献边界、项目真实性、平台迁移能力、指标口径、工程落地深度。

专业约束：
- 不要输出匹配分，不要输出 score，不要输出 score_breakdown，避免伪精确。
- 不要编造简历中不存在的信息；没有证据时应放入 possible_gaps 或 technical_risks。
- risks 和 interview_focus 只能关注岗位相关能力、项目真实性、个人贡献、工程落地、内容增长、Agent/RAG/工具编排/评测观测等业务或技术事项。
- 不要输出年龄、性别、学历届别、到岗时间、出勤时长、未来日期、求职资格等非技术面试事项。
- 结论要服务于“下一步面试应该验证什么”，而不是泛泛评价候选人好坏。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- match_level 只能是 high / medium / low。
- key_experiences_to_probe 中每项包含 name, type, match_reason, matched_keywords。

JD:
{jd}

简历:
{resume}

输出字段：
match_level, recommendation, matched_capabilities, possible_gaps, nice_to_have_matches,
strengths, technical_risks, interview_focus, key_experiences_to_probe。
"""
    data = extract_json(llm.complete("你是严谨的技术面试前分析器。你的回复必须是合法 JSON 对象。", prompt), fallback)
    return _sanitize_match_analysis(_merge_match_defaults(fallback, data))


def _rule_based_match(jd: dict, resume: dict) -> dict:
    jd_must = _unique(jd.get("required_skills", jd.get("must_have_skills", [])))
    jd_nice = _unique(jd.get("preferred_skills", jd.get("nice_to_have_skills", [])))
    resume_skills = _unique(resume.get("skills", []))

    matched = _intersection(resume_skills, jd_must)
    missing = [skill for skill in jd_must if skill.lower() not in {item.lower() for item in matched}]
    nice_matches = _intersection(resume_skills, jd_nice)

    experiences = _collect_experiences(resume)
    relevant_experiences = _rank_experiences(experiences, matched + jd_must)
    match_level = _match_level(matched, jd_must, relevant_experiences)

    risks = []
    if missing:
        risks.append(f"JD 关键能力未完全覆盖：{', '.join(missing[:5])}")
    if not relevant_experiences:
        risks.append("简历中缺少与 JD 技术栈高度相关的项目或实习经历")
    risks.extend(_build_experience_risks(relevant_experiences))

    return {
        "match_level": match_level,
        "recommendation": _recommendation(match_level),
        "matched_capabilities": matched,
        "matched_skills": matched,  # compatibility for planner/interviewer
        "possible_gaps": missing,
        "missing_required_skills": missing,  # compatibility
        "nice_to_have_matches": nice_matches,
        "strengths": _build_strengths(matched, relevant_experiences),
        "technical_risks": risks,
        "risks": risks,  # compatibility
        "interview_focus": _build_recommended_focus(matched, missing, relevant_experiences),
        "recommended_focus": _build_recommended_focus(matched, missing, relevant_experiences),  # compatibility
        "key_experiences_to_probe": relevant_experiences[:5],
    }


def _sanitize_match_analysis(match: dict) -> dict:
    blocked = [
        "未来日期",
        "时间线",
        "到岗",
        "出勤",
        "2027届",
        "2027 届",
        "在读硕士",
        "性别",
        "年龄",
        "出生",
        "求职资格",
    ]
    match.pop("score", None)
    match.pop("score_breakdown", None)
    for key in ["risks", "technical_risks", "recommended_focus", "interview_focus", "possible_gaps", "strengths"]:
        values = match.get(key)
        if isinstance(values, list):
            match[key] = [
                item
                for item in values
                if not any(word in str(item) for word in blocked)
            ]

    if not match.get("matched_capabilities") and match.get("matched_skills"):
        match["matched_capabilities"] = match["matched_skills"]
    if not match.get("matched_skills") and match.get("matched_capabilities"):
        match["matched_skills"] = match["matched_capabilities"]
    if not match.get("possible_gaps") and match.get("missing_required_skills"):
        match["possible_gaps"] = match["missing_required_skills"]
    if not match.get("missing_required_skills") and match.get("possible_gaps"):
        match["missing_required_skills"] = match["possible_gaps"]
    if not match.get("technical_risks") and match.get("risks"):
        match["technical_risks"] = match["risks"]
    if not match.get("risks") and match.get("technical_risks"):
        match["risks"] = match["technical_risks"]
    if not match.get("interview_focus") and match.get("recommended_focus"):
        match["interview_focus"] = match["recommended_focus"]
    if not match.get("recommended_focus") and match.get("interview_focus"):
        match["recommended_focus"] = match["interview_focus"]
    if "match_level" not in match:
        match["match_level"] = "medium"
    if not match.get("technical_risks"):
        match["technical_risks"] = ["需要验证项目真实性、个人贡献边界和工程落地深度"]
        match["risks"] = match["technical_risks"]
    return match


def _merge_match_defaults(fallback: dict, data: Any) -> dict:
    if not isinstance(data, dict):
        return fallback
    merged = fallback.copy()
    for key, value in data.items():
        if value not in (None, "", []):
            merged[key] = value
    return merged


def _unique(items: Iterable[Any]) -> list[str]:
    result = []
    seen = set()
    for item in items or []:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _intersection(left: list[str], right: list[str]) -> list[str]:
    right_map = {item.lower(): item for item in right}
    return [right_map[item.lower()] for item in left if item.lower() in right_map]


def _collect_experiences(resume: dict) -> list[dict]:
    experiences = []
    for source in ["internships", "projects", "papers", "competitions"]:
        for item in resume.get(source, []) or []:
            if isinstance(item, dict):
                experiences.append({"type": source, **item})
            else:
                experiences.append({"type": source, "name": str(item), "description": str(item)})
    return experiences


def _rank_experiences(experiences: list[dict], keywords: list[str]) -> list[dict]:
    unique_keywords = _unique(keywords)
    ranked = []
    for exp in experiences:
        text = " ".join(str(value) for value in exp.values()).lower()
        hits = [keyword for keyword in unique_keywords if keyword and keyword.lower() in text]
        if hits:
            item = exp.copy()
            item["matched_keywords"] = hits
            item["match_reason"] = f"与 JD 技术栈相关：{', '.join(hits[:6])}"
            ranked.append(item)
    ranked.sort(key=lambda item: len(item.get("matched_keywords", [])), reverse=True)
    return ranked


def _match_level(matched: list[str], required: list[str], experiences: list[dict]) -> str:
    ratio = len(matched) / max(len(required), 1)
    if ratio >= 0.7 and experiences:
        return "high"
    if ratio >= 0.4 or experiences:
        return "medium"
    return "low"


def _recommendation(match_level: str) -> str:
    if match_level == "high":
        return "能力方向高度相关，建议围绕关键经历进行深挖验证"
    if match_level == "medium":
        return "能力方向部分匹配，建议通过面试确认缺口和工程深度"
    return "能力方向匹配较弱，建议优先验证 JD 核心能力是否具备"


def _build_strengths(matched: list[str], experiences: list[dict]) -> list[str]:
    strengths = []
    if matched:
        strengths.append(f"简历覆盖 JD 关键能力：{', '.join(matched[:8])}")
    if experiences:
        names = [str(item.get("name") or item.get("description") or item.get("type")) for item in experiences[:3]]
        strengths.append(f"存在与岗位相关的经历可深挖：{', '.join(names)}")
    return strengths


def _build_recommended_focus(matched: list[str], missing: list[str], experiences: list[dict]) -> list[str]:
    focus = ["个人贡献边界", "项目真实性", "工程落地细节"]
    focus.extend([f"{skill} 场景应用" for skill in matched[:5]])
    focus.extend([f"验证 {skill} 是否具备基础能力" for skill in missing[:3]])
    if experiences:
        focus.append("围绕最高相关经历追问技术选型、指标和复盘")
    return list(dict.fromkeys(focus))


def _build_experience_risks(experiences: list[dict]) -> list[str]:
    risks = []
    for exp in experiences[:5]:
        for point in exp.get("unclear_points", []) or []:
            risks.append(f"{exp.get('name', '相关经历')}：{point}")
    return list(dict.fromkeys(risks))
