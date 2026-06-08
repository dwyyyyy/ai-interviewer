from __future__ import annotations

from copy import deepcopy

from src.defaults import DEFAULT_INTERVIEW_CONFIG
from src.json_utils import extract_json
from src.llm_client import LLMClient


def build_interview_config(llm: LLMClient, requirement_text: str | None) -> dict:
    fallback = deepcopy(DEFAULT_INTERVIEW_CONFIG)
    if not requirement_text or not requirement_text.strip() or not llm.available:
        return fallback

    prompt = f"""
请把用户的自然语言面试要求解析成结构化配置。
如果用户没有明确说明某项，请使用默认值。只输出 JSON，不要解释。

要求：
1. target_rounds 表示建议轮次，不是固定轮次。
2. 如果用户要求“快速演示”“简单跑通”，可降低 target_rounds。
3. 如果用户要求“深挖”“严格”“完整技术面”，可提高 target_rounds，但不要超过默认 max_rounds。
4. stages 中的 demo_rounds 是阶段建议轮次，后续 Interview Memory 仍可根据回答质量提前结束或追问延展。

默认配置：
{fallback}

用户要求：
{requirement_text}
"""
    data = extract_json(
        llm.complete("你是面试配置解析器，只输出 JSON。", prompt),
        fallback,
    )
    return _merge_defaults(fallback, data)


def _merge_defaults(default: dict, data: dict) -> dict:
    merged = deepcopy(default)
    if isinstance(data, dict):
        merged["interviewer"].update(data.get("interviewer", {}))
        if "interview_flow" in data:
            merged["interview_flow"].update(data["interview_flow"])
            if data["interview_flow"].get("stages"):
                merged["interview_flow"]["stages"] = data["interview_flow"]["stages"]
    return merged
