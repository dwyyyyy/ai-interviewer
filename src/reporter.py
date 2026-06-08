from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import InterviewMemory


def build_report(llm: LLMClient, role: dict, plan: dict, memory: InterviewMemory, final_profile: dict) -> dict:
    communication_observations = _communication_observations(memory)
    fallback = {
        "overall_evaluation": final_profile.get("candidate_summary", "建议人工复核完整问答记录。"),
        "job_match": {
            "level": final_profile.get("match_level", "需要结合面试证据判断"),
            "summary": final_profile.get("recommendation", "建议结合最终报告判断是否进入下一轮。"),
            "validated_strengths": final_profile.get("validated_strengths", []) or memory.collect_strengths(),
            "remaining_gaps": final_profile.get("validated_risks", memory.open_risks),
        },
        "communication": {
            "summary": "基于回答结构、具体程度和证据表达生成的沟通观察。",
            "observations": communication_observations,
            "risks": _communication_risks(memory),
        },
        "potential_risks": final_profile.get("validated_risks", memory.open_risks),
        "direction_scores": [score.model_dump() for score in memory.direction_scores],
        "good_performance": final_profile.get("validated_strengths", []) or memory.collect_observations(),
        "weak_performance": memory.open_risks,
        "technical_risks": final_profile.get("validated_risks", memory.open_risks),
        "evidence_chain": [
            {
                "round": turn.round,
                "stage": turn.stage_name,
                "question": turn.question,
                "answer_summary": turn.evaluation.answer_summary,
                "observations": turn.evaluation.observations,
                "missing_points": turn.evaluation.missing_points,
                "risks": turn.evaluation.risk_flags,
            }
            for turn in memory.conversation
        ],
        "next_round_suggestions": final_profile.get("next_round_focus", []),
        "recommendation": final_profile.get("recommendation", "建议结合证据链判断是否进入下一轮。"),
    }
    fallback["readable_report"] = _build_readable_report(fallback)
    if not llm.available:
        return fallback

    prompt = f"""
你是一名专业招聘评估顾问，负责基于完整面试记忆生成最终面试评估报告。

报告原则：
1. 结论必须基于面试证据链，不要编造未被回答支持的信息。
2. 不输出每题分数，也不要输出总分，避免伪精确。
3. 区分“简历声称”“面试已验证”和“仍需下一轮验证”的内容。
4. 风险点应表述为岗位相关的待验证事项，例如项目真实性、个人贡献、指标口径、平台迁移能力、工程落地深度。
5. 下一轮建议要具体可执行，能指导面试官继续考察。

要求包含：
overall_evaluation, job_match, communication, potential_risks, good_performance,
weak_performance, technical_risks, direction_scores, evidence_chain, next_round_suggestions, recommendation, readable_report。

字段说明：
- job_match: 包含 level, summary, validated_strengths, remaining_gaps。
- communication: 包含 summary, observations, risks，重点看表达结构、具体程度和证据意识。
- potential_risks: 只列技术能力、项目真实性、个人贡献、工程落地相关风险。
- direction_scores: 汇总每个考察大方向的 1-4 档验证等级、证据、缺失点和下一轮建议。
- readable_report: 面向招聘负责人阅读的 Markdown 文本报告，不要写成 JSON 风格。结构建议包含：总体结论、岗位匹配、方向验证结果、主要风险、下一轮建议。

面试官：{role}
面试计划：{plan}
最终画像：{final_profile}
面试记忆：{memory.model_dump()}

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
"""
    data = extract_json(llm.complete("你是专业的招聘面试评估报告生成器。", prompt), fallback)
    report = _merge_report_defaults(fallback, data)
    if not report.get("readable_report"):
        report["readable_report"] = _build_readable_report(report)
    return report


def _communication_observations(memory: InterviewMemory) -> list[str]:
    observations = []
    for turn in memory.conversation:
        answer_len = len(turn.answer.strip())
        if answer_len >= 120:
            observations.append(f"第 {turn.round} 轮回答信息量较充分，能支撑进一步判断。")
        elif answer_len < 50:
            observations.append(f"第 {turn.round} 轮回答偏短，需要继续观察表达结构和细节展开能力。")
    return observations[:6] or ["需要结合更多轮次观察沟通表达。"]


def _communication_risks(memory: InterviewMemory) -> list[str]:
    risks = []
    short_answers = [turn.round for turn in memory.conversation if len(turn.answer.strip()) < 50]
    if short_answers:
        risks.append(f"第 {', '.join(map(str, short_answers[:5]))} 轮回答偏短，可能缺少结构化表达或细节展开。")
    if not risks:
        risks.append("暂未发现明显沟通风险。")
    return risks


def _merge_report_defaults(fallback: dict, data: object) -> dict:
    if not isinstance(data, dict):
        return fallback
    merged = fallback.copy()
    for key, value in data.items():
        if value not in (None, "", []):
            merged[key] = value
    return merged


def _build_readable_report(report: dict) -> str:
    lines = ["## 面试评估报告", ""]
    lines.append("### 总体结论")
    lines.append(str(report.get("overall_evaluation") or report.get("recommendation") or "建议结合证据链人工复核。"))
    lines.append("")

    job_match = report.get("job_match", {}) or {}
    lines.append("### 岗位匹配")
    lines.append(f"- 匹配判断：{job_match.get('level', '需要结合面试证据判断')}")
    if job_match.get("summary"):
        lines.append(f"- 结论摘要：{job_match['summary']}")
    for item in job_match.get("validated_strengths", [])[:5]:
        lines.append(f"- 已验证优势：{item}")
    for item in job_match.get("remaining_gaps", [])[:5]:
        lines.append(f"- 待验证缺口：{item}")
    lines.append("")

    communication = report.get("communication", {}) or {}
    lines.append("### 沟通表现")
    lines.append(str(communication.get("summary") or "需要结合更多问答观察沟通表达。"))
    for item in communication.get("observations", [])[:5]:
        lines.append(f"- {item}")
    for item in communication.get("risks", [])[:3]:
        lines.append(f"- 风险：{item}")
    lines.append("")

    scores = report.get("direction_scores", []) or []
    lines.append("### 方向验证结果")
    if scores:
        for score in scores:
            lines.append(
                f"- {score.get('direction', '未命名方向')}：{score.get('level_label', '未验证')}"
                f"（{score.get('verification_level', '-')} / 4）"
            )
            if score.get("judgement"):
                lines.append(f"  - 判断：{score['judgement']}")
            if score.get("suggestion"):
                lines.append(f"  - 建议：{score['suggestion']}")
    else:
        lines.append("- 暂无方向评分。")
    lines.append("")

    risks = report.get("potential_risks", []) or report.get("technical_risks", []) or []
    lines.append("### 主要风险")
    if risks:
        for item in risks[:6]:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂未记录明显风险。")
    lines.append("")

    suggestions = report.get("next_round_suggestions", []) or []
    lines.append("### 下一轮建议")
    if suggestions:
        for item in suggestions[:6]:
            lines.append(f"- {item}")
    else:
        lines.append("- 建议结合未闭环风险继续追问关键经历、个人贡献和指标证据。")
    return "\n".join(lines)
