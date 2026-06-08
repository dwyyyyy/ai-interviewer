from __future__ import annotations

import re

from src.json_utils import extract_json
from src.llm_client import LLMClient


def structure_jd(llm: LLMClient, jd_text: str) -> dict:
    preferred_skills = _extract_nice_skills(jd_text)
    required_skills = [skill for skill in _extract_common_skills(jd_text) if skill not in preferred_skills]
    fallback = {
        "job_title": _guess_job_title(jd_text),
        "business_context": _extract_business_context(jd_text),
        "responsibilities": _extract_bullets(jd_text, ["具体职责", "职责"]),
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "core_capabilities": _extract_core_capabilities(jd_text),
    }
    if not llm.available:
        return fallback
    prompt = f"""
你是一名招聘需求分析专家，负责将非结构化 JD 解析为后续匹配和面试规划可使用的标准化字段。

任务目标：
1. 只抽取 JD 原文中明确出现或可直接归纳的信息，不要补充常识、推测候选人要求或创造新条件。
2. 区分必备要求与加分项：required_skills 放任职要求中的硬性能力，preferred_skills 放“优先、加分、bonus”等非硬性条件。
3. business_context 只描述岗位所在业务场景或业务域，例如 B2B 平台、供应链定制找工厂、新媒体内容矩阵；不要复述整段 JD。
4. responsibilities 保留岗位职责中的关键动作，避免长篇照抄。
5. core_capabilities 抽象为岗位真正要考察的能力维度，例如内容矩阵操盘、AI 提效、数据增长、业务流程重构。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 缺失字段使用空数组或 "unknown"。
- 只能输出字段：job_title, business_context, responsibilities, required_skills, preferred_skills, core_capabilities。
- 不要输出以下字段：agent_related_requirements, evaluation_focus, must_have_skills, nice_to_have_skills, experience_requirements, business_scenarios, seniority_level。

JD：
{jd_text[:8000]}
"""
    data = _keep_keys(
        extract_json(llm.complete("你是严谨的招聘 JD 解析器。你的回复必须是合法 JSON 对象。", prompt), fallback),
        {"job_title", "business_context", "responsibilities", "required_skills", "preferred_skills", "core_capabilities"},
        fallback,
    )
    return _normalize_jd(data, fallback)


def structure_resume(llm: LLMClient, resume_text: str) -> dict:
    fallback = {
        "candidate_name": _extract_name(resume_text),
        "skills": _extract_common_skills(resume_text),
        "education": _extract_education(resume_text),
        "internships": _extract_work_or_internship_blocks(resume_text),
        "projects": _extract_experience_blocks(resume_text, "项目经历"),
        "papers": _extract_experience_blocks(resume_text, "论文"),
        "competitions": _extract_experience_blocks(resume_text, "竞赛"),
        "raw_summary": resume_text[:1400],
    }
    if not llm.available:
        return fallback
    prompt = f"""
你是一名候选人履历结构化分析专家，负责把简历原文转换为可用于岗位匹配和面试追问的事实字段。

任务目标：
1. 只抽取简历原文中存在的信息，不要替候选人补充经历、技能、成绩或结论。
2. skills 提取候选人明确体现的工具、平台、技术栈、方法论和业务能力。
3. education 保留学校、专业、学历、时间、核心课程或奖项等事实信息。
4. internships 字段用于保存实习经历或工作经历；如果简历标题是“工作经历”“工作经验”“职业经历”，也要归入 internships。
5. projects 用于保存可被面试深挖的项目、作品、运营案例、自动化工具或业务成果。
6. claimed_contribution 只记录候选人声称本人负责的内容；如果个人贡献不清，填 "unknown"。
7. unclear_points 记录简历表达中需要后续面试澄清的事实模糊点，例如指标口径、个人贡献边界、工具实现方式，不要做价值判断。

输出要求：
- 只输出合法 JSON 对象。
- 禁止输出 Markdown、解释、注释、代码块。
- 缺失字段使用空数组或 "unknown"。
- 只能输出字段：candidate_name, skills, education, internships, projects, papers, competitions。
- projects 中尽量包含 name, description, tech_stack, claimed_contribution, unclear_points。

简历：
{resume_text[:10000]}
"""
    return extract_json(llm.complete("你是严谨的简历解析器。你的回复必须是合法 JSON 对象。", prompt), fallback)


def _guess_job_title(text: str) -> str:
    if "Agent" in text or "AI" in text or "大模型" in text:
        return "AI Agent 应用工程师"
    return "unknown"


def _keep_keys(data: dict, allowed_keys: set[str], fallback: dict) -> dict:
    cleaned = {}
    for key in allowed_keys:
        value = data.get(key)
        cleaned[key] = fallback.get(key, []) if value in (None, "", [], "unknown") else value
    return {key: cleaned[key] for key in fallback.keys()}


def _normalize_jd(data: dict, fallback: dict) -> dict:
    data["required_skills"] = _as_list(data.get("required_skills"))
    data["preferred_skills"] = _as_list(data.get("preferred_skills"))
    data["responsibilities"] = _as_list(data.get("responsibilities"))
    data["core_capabilities"] = _as_list(data.get("core_capabilities"))

    if not data["preferred_skills"]:
        data["preferred_skills"] = fallback.get("preferred_skills", [])
    if not data["core_capabilities"]:
        data["core_capabilities"] = fallback.get("core_capabilities", [])

    preferred_lower = {skill.lower() for skill in data["preferred_skills"]}
    data["required_skills"] = [
        skill for skill in data["required_skills"]
        if skill.lower() not in preferred_lower
    ]
    return data


def _as_list(value) -> list:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, "", "unknown"):
        return []
    return [str(value).strip()]


def _extract_name(text: str) -> str:
    match = re.search(r"姓名[:：]\s*([^\s\n]+)", text)
    return match.group(1).strip() if match else "unknown"


def _extract_common_skills(text: str) -> list[str]:
    skill_patterns = {
        "Agent": [r"\bAgent\b", "智能体"],
        "LangGraph": ["LangGraph"],
        "LangChain": ["LangChain"],
        "MCP": [r"\bMCP\b"],
        "Skills": [r"\bSkills?\b", "技能生态"],
        "Memory": [r"\bMemory\b", "记忆"],
        "Agent Harness": ["Agent Harness", r"\bHarness\b"],
        "RAG": [r"\bRAG\b", "知识库", "召回"],
        "Prompt Engineering": ["Prompt Engineering", "Prompt", "提示词"],
        "Context Engineering": ["Context Engineering", "上下文"],
        "Tool Calling": ["工具调用", "函数调用", "Tool-Use", "Tool Use"],
        "ReAct": ["ReAct"],
        "Reflection": ["反思", "纠错"],
        "LLM": [r"\bLLM\b", "大模型"],
        "OpenSearch": ["OpenSearch"],
        "Qdrant": ["Qdrant"],
        "向量检索": ["向量检索", "KNN", "Embedding"],
        "BM25": ["BM25"],
        "RRF": ["RRF"],
        "ES": [r"\bES\b", "Elasticsearch"],
        "API": [r"\bAPI\b", "SDK"],
        "Python": ["Python"],
        "Java": ["Java"],
        "JavaScript": ["JavaScript", r"\bJS\b", "Node"],
        "FastAPI": ["FastAPI"],
        "MySQL": ["MySQL", "MySql"],
        "Redis": ["Redis"],
        "MQ": [r"\bMQ\b", "RocketMQ", "RabbitMQ", "Kafka"],
        "RocketMQ": ["RocketMQ"],
        "RabbitMQ": ["RabbitMQ"],
        "Kafka": ["Kafka"],
        "Docker": ["Docker"],
        "Kubernetes": ["Kubernetes", r"\bK8s\b"],
        "vLLM": ["vLLM"],
        "Ollama": ["Ollama"],
        "KV Cache": ["KV cache", "KV Cache"],
        "SFT": [r"\bSFT\b"],
        "RL": [r"\bRL\b", "强化学习"],
    }
    found = []
    for skill, patterns in skill_patterns.items():
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            found.append(skill)
    return found


def _extract_nice_skills(text: str) -> list[str]:
    bonus_text = text
    bonus_markers = ["加分项", "优先", "plus"]
    for marker in bonus_markers:
        index = text.find(marker)
        if index >= 0:
            bonus_text = text[index:]
            break
    bonus_keywords = ["vLLM", "Ollama", "KV Cache", "SFT", "RL", "多智能体", "MCP", "Skills"]
    return [skill for skill in bonus_keywords if re.search(re.escape(skill), bonus_text, flags=re.I)]


def _extract_business_context(text: str) -> str:
    lines = [line.strip("；;。 ") for line in text.splitlines() if line.strip()]
    for line in lines:
        if any(keyword in line for keyword in ["背景", "目标", "业务", "场景", "你将"]):
            return line[:300]
    return text[:300]


def _extract_core_capabilities(text: str) -> list[str]:
    capabilities = []
    capability_keywords = {
        "需求理解与问题定义": ["需求理解", "问题定义", "痛点", "归因"],
        "AI 系统架构设计": ["架构设计", "AI 原生系统", "系统架构"],
        "RAG 与知识库构建": ["RAG", "知识库", "召回", "上下文注入"],
        "Agent 记忆与工具编排": ["记忆", "工具编排", "工具调用", "Agent"],
        "任务拆解与反思纠错": ["任务拆解", "反思", "纠错"],
        "评测回测与效果优化": ["评测", "回测", "效果", "调优"],
        "工程落地与稳定性": ["工程", "高并发", "异步", "降级", "稳定"],
    }
    for capability, keywords in capability_keywords.items():
        if any(keyword in text for keyword in keywords):
            capabilities.append(capability)
    return capabilities


def _extract_bullets(text: str, markers: list[str]) -> list[str]:
    lines = [line.strip("；;。 ") for line in text.splitlines() if line.strip()]
    selected = []
    marker_hit = False
    for line in lines:
        if any(marker in line for marker in markers):
            marker_hit = True
            continue
        if marker_hit and re.match(r"^(\d+\.|[-•●])", line):
            selected.append(re.sub(r"^(\d+\.|[-•●])\s*", "", line))
        if marker_hit and len(selected) >= 8:
            break
    return selected


def _extract_education(text: str) -> list[dict]:
    education = []
    for school in ["西安电子科技大学", "天津理工大学"]:
        if school in text:
            education.append({"school": school, "raw": _line_window(text, school)})
    return education


def _extract_experience_blocks(text: str, section_name: str) -> list[dict]:
    section = _slice_section(text, section_name)
    if not section:
        return []

    blocks = []
    if section_name == "实习经历":
        blocks.append(
            {
                "name": _first_nonempty_line(section) or "实习经历",
                "description": section[:900],
                "tech_stack": _extract_common_skills(section),
                "claimed_contribution": _extract_claimed_contribution(section),
                "unclear_points": _infer_unclear_points(section),
            }
        )
        return blocks

    project_chunks = re.split(r"\n(?=[^\n]{4,40}\n20\d{2}\.\d{2})", section)
    for chunk in project_chunks:
        chunk = chunk.strip()
        if len(chunk) < 20:
            continue
        blocks.append(
            {
                "name": _first_nonempty_line(chunk) or section_name,
                "description": chunk[:1000],
                "tech_stack": _extract_common_skills(chunk),
                "claimed_contribution": _extract_claimed_contribution(chunk),
                "unclear_points": _infer_unclear_points(chunk),
            }
        )
    return blocks[:5]


def _extract_work_or_internship_blocks(text: str) -> list[dict]:
    for section_name in ["实习经历", "工作经历", "工作经验", "职业经历"]:
        blocks = _extract_experience_blocks(text, section_name)
        if blocks:
            return blocks
    return []


def _slice_section(text: str, section_name: str) -> str:
    section_headers = ["教育背景", "专业技能", "实习经历", "工作经历", "工作经验", "职业经历", "项目经历", "论文", "竞赛", "获奖", "校园经历"]
    start = text.find(section_name)
    if start < 0:
        return ""
    end_candidates = [text.find(header, start + len(section_name)) for header in section_headers if text.find(header, start + len(section_name)) > 0]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start + len(section_name) : end].strip()


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip("：: •●\t ")
        if line and not re.match(r"^20\d{2}", line):
            return line[:80]
    return ""


def _line_window(text: str, keyword: str) -> str:
    index = text.find(keyword)
    if index < 0:
        return ""
    return text[max(0, index - 80) : index + 180]


def _extract_claimed_contribution(text: str) -> str:
    patterns = [
        r"负责部分[:：]([^\n]+)",
        r"本人负责([^\n]+)",
        r"负责([^\n。；]+)",
        r"参与([^\n。；]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip()
    return "unknown"


def _infer_unclear_points(text: str) -> list[str]:
    unclear = []
    if not re.search(r"(指标|提升|降低|准确率|召回率|QPS|延迟|耗时|成本)", text, flags=re.I):
        unclear.append("缺少量化效果指标")
    if "负责" not in text and "本人" not in text:
        unclear.append("个人贡献边界需要确认")
    if not re.search(r"(上线|部署|观测|监控|回测|评测|稳定)", text):
        unclear.append("工程化落地和稳定性经验需要验证")
    return unclear
