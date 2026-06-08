from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import InterviewMemory


def build_pre_interview_brief(
    llm: LLMClient,
    jd: dict,
    resume: dict,
    config: dict,
    match_analysis: dict,
) -> dict:
    fallback = {
        "candidate_name": resume.get("candidate_name", "unknown"),
        "target_role": jd.get("job_title", "unknown"),
        "brief_summary": "基于简历与 JD 匹配分析生成的面试前简报。首次面试前不生成候选人画像，只整理待验证信息。",
        "claimed_skills": resume.get("skills", []),
        "matched_skills": match_analysis.get("matched_skills", []),
        "pre_interview_strengths": match_analysis.get("strengths", []),
        "verification_hypotheses": match_analysis.get("risks", []),
        "priority_verification_points": match_analysis.get(
            "interview_focus",
            ["个人贡献", "项目真实性", "技术细节", "工程落地"],
        ),
        "match_level": match_analysis.get("match_level", "medium"),
        "match_recommendation": match_analysis.get("recommendation", "建议通过面试进一步验证"),
    }
    if not llm.available:
        return fallback

    prompt = f"""
你是一名招聘面试准备专家，负责基于 JD、简历和匹配分析生成面试前简报。

设计原则：
1. 首次面试前不要生成候选人画像，不要做最终评价。
2. 只整理候选人简历声称的能力、与岗位的初步匹配点、待验证假设和建议追问方向。
3. 所有判断都必须保持“待验证”口径，真正的候选人画像只能在面试结束后基于 Interview Memory 生成。
4. verification_hypotheses 表示面试中需要验证的问题，不是最终风险结论。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 只能输出字段：candidate_name, target_role, brief_summary, claimed_skills, matched_skills, pre_interview_strengths, verification_hypotheses, priority_verification_points, match_level, match_recommendation。

JD：{jd}
简历：{resume}
匹配分析：{match_analysis}
配置：{config}
"""
    return extract_json(llm.complete("你是专业的招聘面试前简报生成器。", prompt), fallback)


def build_final_profile(llm: LLMClient, pre_interview_brief: dict, plan: dict, memory: InterviewMemory) -> dict:
    direction_scores = [score.model_dump() for score in memory.direction_scores]
    fallback = {
        "candidate_summary": "基于面试记录生成的最终画像。",
        "match_level": pre_interview_brief.get("match_level", "medium"),
        "validated_strengths": memory.collect_strengths(),
        "validated_risks": memory.open_risks,
        "observations": memory.collect_observations(),
        "direction_scores": direction_scores,
        "recommendation": "建议结合最终报告判断是否进入下一轮。",
        "next_round_focus": memory.open_risks[:5],
    }
    if not llm.available:
        return fallback

    prompt = f"""
你是一名招聘评估专家，请基于面试前简报、面试计划和完整面试记忆生成最终候选人画像。

要求：
1. 候选人画像必须来自面试行为证据和完整问答记忆。
2. 区分“简历声称”“面试已验证”“仍需下一轮验证”的内容。
3. 所有判断尽量引用轮次证据，不要把面试前简报当作最终结论。
4. direction_scores 必须保留每个大方向的 1-4 档验证等级、评语、证据、缺失点和建议。
5. 只输出 JSON。

输出字段：
candidate_summary, match_level, validated_strengths, validated_risks,
observations, direction_scores, recommendation, next_round_focus。

面试前简报：{pre_interview_brief}
面试计划：{plan}
面试记忆：{memory.model_dump()}
"""
    data = extract_json(llm.complete("你是最终候选人画像生成器。", prompt), fallback)
    if isinstance(data, dict) and not data.get("direction_scores"):
        data["direction_scores"] = direction_scores
    return data
