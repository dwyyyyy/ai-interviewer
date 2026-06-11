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
8. 题库候选题只能作为参考角度，不能直接照搬题库问题。
9. 如果题库问题中的概念没有出现在候选人经历、JD 或当前考察方向中，禁止把该概念写进最终问题。例如经历里没有“长短期记忆”，就不能问“长短期记忆怎么设计”。
10. 最终问题必须是一段自然中文，不要包含“项目背景参考：”这类系统提示，不要把简历原文大段贴给候选人。
11. 当前考察方向如果来自项目/实习深挖，问题要体现技术拷打：优先追问本人实现边界、核心数据流/调用链、接口或 Prompt/Agent 编排、异常处理、权限/成本/性能、指标结果，不要只问“你怎么做的”。
12. 问题里必须点名当前项目中的具体技术对象或业务对象，例如 MCP 工具、MySQL 查询、Data Analyze Agent、RAG、Prompt、自动化脚本、内容 SOP、平台增长指标等；如果上下文没有该对象，不要硬编。
13. 一次只问一个主问题，但问题要足够尖锐，能逼出可验证细节，例如“你亲自写了哪一段”“输入输出是什么”“失败分支怎么处理”“指标怎么定义和验证”。

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
    topic = probe.get("target_capability") or memory.current_stage_name
    project_hint = _project_hint_from_probe(probe)
    detail = probe.get("source_detail")
    direction = probe.get("probe_direction", topic)
    detail_hint = _compact_detail_hint(detail)
    target = _technical_target_from_probe(probe)
    if "个人贡献" in direction or "真实性" in direction or "本人实现边界" in direction:
        question = (
            f"围绕{project_hint}{detail_hint}里的{target}，请说清楚你本人具体实现了哪几个模块，"
            f"哪些代码、配置、Prompt 或接口是你亲自完成的，哪些部分是团队或现成组件提供的？"
        )
    elif "方法" in direction or "执行" in direction or "链路" in direction or "数据流" in direction or "调用链" in direction:
        question = (
            f"请围绕{project_hint}{detail_hint}里的{target}，按真实链路讲清楚输入是什么、经过哪些工具或接口调用、"
            f"中间数据怎么处理、最终输出是什么，并说明当时为什么这样设计。"
        )
    elif "结果" in direction or "指标" in direction or "复盘" in direction or "异常" in direction:
        question = (
            f"针对{project_hint}{detail_hint}里的{target}，请讲一个实际遇到的异常或效果不稳定 case，"
            f"你当时怎么定位和处理，最后用什么指标证明方案有效？"
        )
    else:
        question = (
            f"请结合{project_hint}{detail_hint}，围绕「{direction}」讲一个最能证明你技术深度的细节："
            f"你具体负责什么，核心实现链路是什么，遇到问题后怎么判断和处理？"
        )
    if memory.consecutive_followups > 0:
        question = (
            f"围绕刚才的回答，请继续补充一个可验证的技术细节：具体到接口、数据结构、Prompt、SQL、"
            f"工具调用或异常分支，你当时是怎么实现和验证的？"
        )
    return {
        "question": question,
        "question_type": "retrieval_augmented_follow_up" if memory.consecutive_followups > 0 else "retrieval_augmented",
        "focus_area": direction,
        "reason": probe.get("reason", "基于题库检索和当前面试阶段生成。"),
        "expected_signal": "候选人好的回答应能说出本人边界、核心链路、关键实现细节、异常处理、指标口径和真实结果。",
        "retrieved_question_ids": _matched_retrieved_ids(probe, retrieved_questions),
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
    result["question"] = _sanitize_question_text(result.get("question", fallback["question"]), probe, fallback["question"])
    if not result.get("retrieved_question_ids"):
        result["retrieved_question_ids"] = _matched_retrieved_ids(probe, retrieved_questions)
    return result


def _compact_detail_hint(detail: str | None) -> str:
    if not detail:
        return ""
    lines = [line.strip() for line in str(detail).splitlines() if line.strip()]
    compact = "；".join(lines[:2])
    return f"（{compact[:80]}）"


def _technical_target_from_probe(probe: dict) -> str:
    context = " ".join(
        str(probe.get(key, ""))
        for key in ["probe_direction", "source_experience", "source_detail", "scenario_context", "target_capability"]
    )
    known_targets = [
        "MCP Server",
        "MCP 工具",
        "Data Analyze Agent",
        "Agent",
        "RAG",
        "MySQL",
        "Prompt",
        "工作流",
        "自动化脚本",
        "数据分析",
        "内容 SOP",
        "ChatGPT",
        "Midjourney",
        "Runway",
        "小红书",
        "抖音",
        "API",
        "Python",
        "SQL",
    ]
    context_lower = context.lower()
    for target in known_targets:
        if target.lower() in context_lower:
            return target
    direction = str(probe.get("probe_direction") or "").strip()
    return direction[:24] if direction else "这个项目"


def _matched_retrieved_ids(probe: dict, retrieved_questions: list[dict]) -> list:
    context = " ".join(
        str(probe.get(key, ""))
        for key in ["probe_direction", "source_experience", "source_detail", "scenario_context", "target_capability"]
    ).lower()
    ids = []
    for item in retrieved_questions:
        text = " ".join(str(item.get(key, "")) for key in ["topic", "question_template", "tags"]).lower()
        if any(token in context for token in _important_tokens(text)):
            if item.get("id"):
                ids.append(item["id"])
    return ids[:3]


def _important_tokens(text: str) -> list[str]:
    tokens = []
    for raw in text.replace("/", " ").replace("|", " ").replace("，", " ").replace("。", " ").split():
        token = raw.strip("：:；;,.()（）[]【】\"'")
        if len(token) >= 3:
            tokens.append(token)
    return tokens


def _sanitize_question_text(question: str, probe: dict, fallback_question: str) -> str:
    text = " ".join(str(question).split())
    context = " ".join(
        str(probe.get(key, ""))
        for key in ["probe_direction", "source_experience", "source_detail", "scenario_context", "target_capability"]
    ).lower()
    unsupported_terms = ["长期记忆", "短期记忆", "任务过程记忆", "memory", "rag", "召回"]
    if any(term.lower() in text.lower() and term.lower() not in context for term in unsupported_terms):
        return fallback_question
    blocked_fragments = ["项目背景参考：", "题库候选题", "Top 10", "请结合「"]
    if any(fragment in text for fragment in blocked_fragments):
        return fallback_question
    return text
