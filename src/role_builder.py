from __future__ import annotations

from src.json_utils import extract_json
from src.llm_client import LLMClient


def build_interviewer_role(llm: LLMClient, jd: dict, config: dict) -> dict:
    fallback = {
        "role": config["interviewer"]["role"],
        "style": config["interviewer"]["style"],
        "tone": config["interviewer"]["tone"],
        "focus_areas": config["interviewer"]["focus_areas"],
        "strictness": config["interviewer"]["scoring_strictness"],
    }
    if not llm.available:
        return fallback
    prompt = f"""
你是一名招聘面试流程设计专家，负责根据岗位需求和用户偏好初始化面试官 Agent。

任务目标：
1. 面试官角色必须贴合岗位类型、业务场景和核心能力要求。
2. tone 需要体现沟通风格，既要专业克制，也要能引导候选人给出事实和证据。
3. focus_areas 应覆盖岗位最关键的能力验证点，不要泛泛罗列。
4. interview_principles 应强调证据链、个人贡献边界、项目真实性、指标口径和可落地性。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 只能输出字段：role, style, tone, focus_areas, strictness, interview_principles。

JD：{jd}
配置：{config["interviewer"]}
"""
    return extract_json(llm.complete("你是专业的招聘面试官 Agent 角色设计器。", prompt), fallback)
