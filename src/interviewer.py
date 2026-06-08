from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient
from src.memory import InterviewMemory
from src.probe_planner import plan_probe_direction
from src.question_composer import compose_question
from src.question_retriever import retrieve_questions


def generate_next_question(
    llm: LLMClient,
    role: dict,
    plan: dict,
    memory: InterviewMemory,
    resume: dict,
    jd: dict,
) -> dict:
    if memory.current_stage_id in {"resume_deep_dive", "tech_stack_scenario"}:
        probe = plan_probe_direction(llm, plan, memory, resume, jd)
        retrieval_query = probe.get("draft_question") or probe.get("query") or probe.get("probe_direction", "")
        retrieved = retrieve_questions(retrieval_query, top_k=10)
        return compose_question(llm, role, plan, memory, resume, jd, probe, retrieved)

    fallback = _fallback_question(memory, plan)
    if not llm.available:
        return fallback

    prompt = f"""
你是一名专业面试官 Agent，负责基于面试角色、面试计划和结构化记忆生成下一轮问题。

任务目标：
1. 每轮只提出一个清晰、可回答、可验证的问题。
2. 问题必须服务于当前面试阶段和未闭环验证点，不要随意发散。
3. 如果上一轮回答暴露出个人贡献不清、指标口径不明、项目真实性不足或业务迁移风险，可以继续追问。
4. 如果已有足够证据，应切换到新的验证点，避免重复盘问。
5. 问题要结合 JD 业务场景和候选人简历经历，避免通用八股题。

面试官角色：{role}
当前阶段：{memory.current_stage}
面试计划：{plan}
记忆摘要：{memory.summary()}
最近 3 轮：{memory.recent_turns()}
已问过的问题：{memory.asked_questions}
简历：{resume}
JD：{jd}

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 不要重复已问过的问题。
- 输出字段：question, question_type, focus_area, reason, expected_signal。
"""
    return extract_json(llm.complete("你是专业的招聘面试官 Agent。", prompt), fallback, )


def _fallback_question(memory: InterviewMemory, plan: dict) -> dict:
    stage_id = memory.current_stage_id
    if stage_id == "self_intro":
        q = "请做一个 3 分钟左右的自我介绍，重点讲和目标岗位最相关的经历。"
        qtype = "opening"
        focus = "自我介绍"
    elif stage_id == "resume_deep_dive":
        if memory.consecutive_followups > 0:
            q = "你刚才提到的这部分，请具体说明你本人负责的模块、关键实现细节，以及遇到的最大问题。"
            qtype = "follow_up"
        else:
            q = "请选择简历中最能代表你能力的一段实习、项目、论文或竞赛经历，讲一下背景、你的个人贡献和最终结果。"
            qtype = "new_topic"
        focus = "简历深挖"
    elif stage_id == "tech_stack_scenario":
        skills = plan.get("matched_tech_stack") or ["MySQL", "Redis", "MQ"]
        skill = skills[min(memory.stage_round_index, len(skills) - 1)]
        q = f"围绕你简历和 JD 中都出现的 {skill}，请结合一个项目场景说明你如何使用它，以及遇到问题时会怎么排查。"
        qtype = "scenario"
        focus = skill
    elif stage_id == "candidate_questions":
        q = "接下来进入反问环节，你可以问我 1-2 个关于岗位、团队、业务或技术方向的问题。"
        qtype = "candidate_question"
        focus = "反问"
    else:
        q = "面试已结束。"
        qtype = "closing"
        focus = "结束"
    return {
        "question": q,
        "question_type": qtype,
        "focus_area": focus,
        "reason": "基于当前阶段和默认策略生成。",
        "expected_signal": "观察候选人是否能给出具体、真实、有证据的回答。",
    }
