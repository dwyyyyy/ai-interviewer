from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import InterviewMemory


def evaluate_answer(
    llm: LLMClient,
    question: dict,
    answer: str,
    plan: dict,
    memory: InterviewMemory,
    resume: dict,
    jd: dict,
) -> dict:
    fallback = _fallback_evaluation(answer)
    if not llm.available:
        return fallback

    prompt = f"""
你是一名专业面试观察员，负责基于本轮问题和候选人回答记录结构化观察，并判断是否需要继续追问。
你不负责给小问题打分，也不负责给大方向做最终评分；最终评分由后台 Direction Scoring Agent 在大方向结束时统一完成。

评估目标：
1. 只基于候选人本轮回答和已有上下文记录证据，不要补充候选人没有说过的内容。
2. 不输出数字分数，不做最终录用判断，不对单个小问题打分。
3. 重点观察回答是否具体、是否有个人贡献、是否有指标证据、是否能解释方案取舍和复盘。
4. 如果回答空泛、个人贡献不清、项目真实性可疑、指标口径不明或 JD 核心能力没答清，则 need_follow_up=true。
5. 如果候选人明确不会、不了解或不是自己负责，则 candidate_admitted_gap=true，并记录对应风险，后续应换题或进入下一验证点。
6. direction_complete 表示当前考察大方向是否已经获得足够判断信号；如果已经问透则为 true，系统会切换到下一个 plan 方向。
7. 如果当前大方向还缺关键证据，direction_complete=false；同时如果适合继续追问，need_follow_up=true。

当前阶段：{memory.current_stage}
面试计划：{plan}
问题：{question}
候选人回答：{answer}
最近记忆：{memory.recent_turns()}
简历摘要：{resume}
JD 摘要：{jd}

输出字段：
answer_summary, observations, missing_points, evidence, strengths, risk_flags,
need_follow_up, direction_complete, signal_sufficient, candidate_admitted_gap, new_information_gain。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- new_information_gain 只能是 low / medium / high。
"""
    return extract_json(llm.complete("你是专业的招聘面试观察记录器。", prompt), fallback)


def _fallback_evaluation(answer: str) -> dict:
    length = len(answer.strip())
    low = length < 50
    admitted_gap = any(word in answer for word in ["不会", "不了解", "没做过", "不熟", "不是我负责"])
    return {
        "answer_summary": answer[:160],
        "observations": ["候选人给出了较具体的回答"] if not low else [],
        "missing_points": ["回答较短，缺少细节"] if low else [],
        "evidence": [answer[:160]] if answer else [],
        "strengths": [],
        "risk_flags": [{"risk": "回答缺少细节", "severity": "medium"}] if low else [],
        "need_follow_up": low and not admitted_gap,
        "direction_complete": not low or admitted_gap,
        "signal_sufficient": not low,
        "candidate_admitted_gap": admitted_gap,
        "new_information_gain": "low" if admitted_gap else "medium",
    }
