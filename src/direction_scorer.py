from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import ConversationTurn


LEVEL_LABELS = {
    1: "未验证",
    2: "部分验证",
    3: "基本验证",
    4: "充分验证",
}


def score_direction(
    llm: LLMClient,
    *,
    direction: str,
    stage: str,
    turns: list[ConversationTurn],
    plan: dict,
    jd: dict,
    resume: dict,
) -> dict:
    fallback = _fallback_score(direction, stage, turns)
    if not turns:
        return fallback
    if not llm.available:
        return fallback

    prompt = f"""
你是一名后台 Direction Scoring Agent，负责对一个已经结束的考察大方向进行 1-4 档验证评价。

评分对象：
- 评分的是 Planner 中的考察大方向，不是单个临时问题。
- 动态问题只是采集证据的手段；请综合该方向下所有问答进行判断。
- 不要逐题评分，不要平均每轮表现；只输出该大方向的统一验证等级和评语。

四档标准：
1 = 未验证：回答空泛、明显回避，或承认不了解/不是本人负责。
2 = 部分验证：能讲概念或局部经历，但缺少关键证据，仍需继续追问。
3 = 基本验证：有真实实践和部分细节，但指标、边界或复盘不够完整。
4 = 充分验证：回答具体，有个人贡献、方法细节、指标证据和复盘思考，可支撑较强判断。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- verification_level 只能是 1 / 2 / 3 / 4。
- level_label 必须与档位对应：未验证、部分验证、基本验证、充分验证。
- suggestion 给出下一轮可执行建议。
- 只能输出字段：direction, stage, verification_level, level_label, judgement, evidence, missing_points, suggestion, confidence, related_rounds。

当前方向：{direction}
当前阶段：{stage}
该方向问答：{[turn.model_dump() for turn in turns]}
面试计划：{plan}
JD：{jd}
简历：{resume}
"""
    data = extract_json(llm.complete("你是专业的招聘面试方向评分器。", prompt), fallback)
    return _merge_score_defaults(fallback, data)


def _fallback_score(direction: str, stage: str, turns: list[ConversationTurn]) -> dict:
    evidence = []
    missing = []
    strengths = []
    for turn in turns:
        evidence.extend(turn.evaluation.evidence)
        missing.extend(turn.evaluation.missing_points)
        strengths.extend(turn.evaluation.strengths)
    has_signal = any(turn.evaluation.signal_sufficient or turn.evaluation.direction_complete for turn in turns)
    admitted_gap = any(turn.evaluation.candidate_admitted_gap for turn in turns)
    if admitted_gap:
        level = 1
    elif has_signal and not missing:
        level = 4
    elif has_signal:
        level = 3
    elif evidence:
        level = 2
    else:
        level = 1
    return {
        "direction": direction,
        "stage": stage,
        "verification_level": level,
        "level_label": LEVEL_LABELS[level],
        "judgement": _fallback_judgement(level, direction),
        "evidence": list(dict.fromkeys(evidence or strengths))[:6],
        "missing_points": list(dict.fromkeys(missing))[:6],
        "suggestion": _fallback_suggestion(level, direction),
        "confidence": "medium",
        "related_rounds": [turn.round for turn in turns],
    }


def _fallback_judgement(level: int, direction: str) -> str:
    if level == 4:
        return f"候选人在「{direction}」方向提供了较充分证据。"
    if level == 3:
        return f"候选人在「{direction}」方向基本可验证，但仍有部分细节需要补充。"
    if level == 2:
        return f"候选人在「{direction}」方向只提供了部分证据，需要继续追问。"
    return f"候选人在「{direction}」方向尚未形成有效验证。"


def _fallback_suggestion(level: int, direction: str) -> str:
    if level >= 3:
        return f"下一轮可围绕「{direction}」的边界条件、复盘和迁移能力继续验证。"
    return f"下一轮建议继续要求候选人围绕「{direction}」补充具体案例、个人贡献和指标证据。"


def _merge_score_defaults(fallback: dict, data: object) -> dict:
    if not isinstance(data, dict):
        return fallback
    merged = fallback.copy()
    for key, value in data.items():
        if value not in (None, "", []):
            merged[key] = value
    try:
        level = int(merged.get("verification_level", 1))
    except (TypeError, ValueError):
        level = 1
    level = max(1, min(level, 4))
    merged["verification_level"] = level
    merged["level_label"] = LEVEL_LABELS[level]
    return merged
