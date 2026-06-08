# AI 模拟面试官 Agent MVP

这是一个面向“智能招聘助手 MVP”笔试题的端到端 Demo，选择场景 B：AI 模拟面试官 Agent。

系统目标不是做一个完整 ATS，而是跑通一条核心闭环：把非结构化的 JD 和简历转成稳定结构化信息，再生成面试计划，进行多轮动态追问，最后输出面试评估报告和可复用的候选人画像。

## 功能概览

- 上传简历 PDF / Word，粘贴 JD 文本。
- 使用 LLM 将 JD 和简历结构化，抽取岗位要求、业务场景、候选人技能、项目、实习/工作经历等。
- 基于结构化 JD 和简历生成面试前匹配分析，识别匹配点、能力缺口和待验证假设。
- 第一轮先让候选人做自我介绍，随后结合 JD、简历、Matcher 和自我介绍生成正式面试计划。
- 面试轮次由正式 plan 中的考察方向数量决定，不固定 8 轮，也不设置固定总轮次。
- 面试过程采用文字交互：面试官展示问题，候选人输入回答。
- 每一轮回答后由 Evaluation Agent 做观察，判断是否需要追问。
- 每个“大方向”结束后，由 Direction Scoring Agent 对该方向下的多轮问答统一评分和写评语。
- 面试结束后生成面向招聘负责人阅读的 Markdown 报告。
- 使用 SQLite 单表保存最近一次面试记忆，包括问答、方向评分、最终候选人画像等。

## 技术栈

- 前端交互：Streamlit
- LLM 接入：OpenAI SDK 兼容接口，可接 OpenAI、Qwen、Kimi、GLM 等兼容 Chat Completions 的模型服务
- 文档解析：PyMuPDF、python-docx
- 结构化建模：Pydantic
- 题库检索：SQLite FTS5 + BM25
- 记忆持久化：SQLite 单表 + JSON 字段
- 配置管理：python-dotenv + `.env`

## 核心技术点

### 1. 结构化优先

JD 和简历不会直接丢给面试 Agent。系统先通过 `src/structurer.py` 把非结构化文本变成 JSON。

JD 结构化字段包括：

- `job_title`：岗位名称
- `business_context`：业务背景
- `responsibilities`：核心职责
- `required_skills`：必备能力
- `preferred_skills`：加分项
- `core_capabilities`：核心能力画像

简历结构化字段包括：

- `candidate_name`：候选人姓名
- `skills`：技能
- `education`：教育经历
- `internships`：实习/工作经历
- `projects`：项目经历
- `papers`：论文
- `competitions`：竞赛/奖项

结构化层只抽取事实，不提前生成风险判断。风险点由 Matcher、Evaluator 和 Direction Scoring Agent 在后续阶段基于证据逐步产生。

### 2. Matcher 只做面试前分析

`src/matcher.py` 负责把 JD 要求和简历事实对齐，输出面试前的匹配分析。

它不做最终录用判断，也不输出分数，主要产出：

- 候选人与岗位匹配的能力点
- 简历中没有充分体现的能力缺口
- 面试中需要验证的假设
- 值得深挖的项目、实习或工作经历
- 建议优先考察的方向

这样设计的原因是：Matcher 的职责是帮助面试开始得更准，而不是在没有问答证据时过早给候选人下结论。

### 3. Planner 在自我介绍后生成“考察地图”

系统开始时只生成一个自我介绍临时计划。候选人完成自我介绍后，`src/planner.py` 再根据 JD、简历、Matcher 结果和自我介绍内容生成正式面试计划。

正式计划不是固定 8 轮，也不是提前写死每一道问题，而是围绕候选人的项目、实习或工作经历生成稳定的大方向：

- `experience_probe_plan`：围绕项目、实习、工作经历生成考察方向。

例如一个项目可能生成 2-3 个方向：

- 个人贡献与真实性
- 方法链路与执行过程
- 结果指标与复盘能力

后续面试过程中，大方向保持稳定，小问题根据候选人具体经历、上一轮回答和题库检索结果动态生成。

轮次控制采用 plan-driven 策略：`experience_probe_plan` 中有多少大方向，就推进多少计划方向；如果某个方向回答不充分，Flow Controller 才会追加追问。项目问完后直接结束并生成报告，不再单独进入业务场景题环节。

### 4. 题库检索辅助动态提问

`src/question_retriever.py` 使用 SQLite FTS5 + BM25 从本地题库取 Top 10 相关问题。

设计原则：

- 检索题库是为了提供参考，不是照抄题库问题。
- 当前考察大方向不变。
- `src/question_composer.py` 会结合候选人的具体项目/经历、当前方向、上一轮回答和题库参考，生成一个更贴合上下文的问题。

这比纯 LLM 生成更稳定，也比固定题单更适合多轮追问。

### 5. 提问、观察、评分分离

系统把面试过程拆成三个角色：

- Interviewer Agent：负责生成当前问题。
- Evaluation Agent：负责观察单轮回答，判断是否需要追问，不打分。
- Direction Scoring Agent：一个大方向结束后，汇总该方向下的多轮问答，给 1-4 档评分和评语。

这样避免每个小问题都打分导致噪声过大。小问题只是采证工具，真正评分对象是 Planner 生成的大方向。

方向评分四档：

```text
1 = 未验证：回答空泛、回避，或明确不是本人负责。
2 = 部分验证：有局部经验，但缺少关键细节或证据。
3 = 基本验证：有真实实践和主要细节，但指标、边界或复盘不够完整。
4 = 充分验证：回答具体，有个人贡献、方法细节、指标证据和复盘思考。
```

### 6. Flow Controller 控制追问与切换

`src/flow_controller.py` 根据 Evaluation Agent 的结构化观察和当前 Memory 状态决定下一步：

- 继续围绕当前方向追问
- 当前方向结束，进入 Direction Scoring Agent
- 切换到下一个计划方向
- 面试结束，生成报告

Memory 只负责记录状态和证据，不负责做流程决策。这样职责更清楚，也方便后续调参。

### 7. 长期记忆设计

系统当前使用一张 SQLite 表 `interview_memory` 保存最近一次面试。

核心保存内容：

- JD 原文、简历原文
- JD / 简历结构化 JSON
- Matcher 结果
- 面试计划
- 多轮问答记录
- 每个大方向的评分与评语
- `final_profile_json`
- 最终展示报告 `report_json`

其中 `final_profile_json` 是长期候选人画像，用于后续面试或后续系统读取。最终 Markdown 报告是给人看的展示材料，不作为长期画像本体。

## 架构图

### 端到端主流程

```mermaid
flowchart TD
    A["输入<br/>JD 文本 + 简历 PDF/Word"] --> B["文档解析<br/>PDF/Word 转文本"]

    B --> C["结构化抽取<br/>JD JSON + Resume JSON"]
    C --> D["匹配分析 Matcher<br/>匹配点 / 缺口 / 待验证假设"]

    D --> E["面试前准备<br/>Pre-interview Brief + 面试官角色"]
    E --> F["第一轮自我介绍<br/>固定简短开场问题"]

    F --> G["Planner<br/>结合 JD / 简历 / Matcher / 自我介绍<br/>生成正式考察地图"]
    G --> H["多轮文字面试<br/>按 plan 大方向动态提问"]

    H --> I["Direction Scoring Agent<br/>每个大方向结束后统一评分"]
    I --> J["面试记忆<br/>记录问答、证据、方向评分"]

    J --> K["最终候选人画像<br/>final_profile_json"]
    J --> L["面试评估报告<br/>Markdown readable_report"]

    K --> M["SQLite interview_memory"]
    L --> M
```

### 面试循环内部

```mermaid
flowchart TD
    A["正式考察计划<br/>experience_probe_plan"] --> B["Probe Planner<br/>选择当前项目大方向"]

    B --> C["Question Retriever<br/>FTS5 + BM25 检索 Top 10"]
    C --> D["Question Composer<br/>结合简历经历和题库参考生成问题"]

    D --> E["候选人文字回答"]
    E --> F["Evaluation Agent<br/>单轮观察，不打分"]

    F --> G{"Flow Controller<br/>下一步决策"}

    G -- "信息不足，需要追问" --> B
    G -- "当前方向已问透" --> H["Direction Scoring Agent<br/>对该方向多轮问答统一评分"]
    H --> I["Memory<br/>写入方向评分和证据"]
    I --> B

    G -- "plan 方向走完" --> J["Reporter<br/>生成最终报告"]
```

### 模块划分

```mermaid
flowchart LR
    UI["app.py<br/>Streamlit UI"] --> Loader["document_loader<br/>PDF/Word 解析"]
    Loader --> Structurer["structurer<br/>JD/简历结构化"]
    Structurer --> Matcher["matcher<br/>面试前匹配分析"]
    Matcher --> Role["role_builder / profile<br/>角色与面试前简报"]
    Role --> Planner["planner<br/>自我介绍后生成正式 plan"]
    Planner --> Interviewer["interviewer<br/>选择方向 + 生成问题"]
    Interviewer --> Retriever["question_retriever<br/>SQLite FTS5/BM25 Top 10"]
    Retriever --> Composer["question_composer<br/>融合经历事实生成问题"]
    Composer --> Evaluator["evaluator<br/>单轮观察"]
    Evaluator --> Flow["flow_controller<br/>追问 / 切换 / 结束"]
    Flow --> Scorer["direction_scorer<br/>大方向评分"]
    Scorer --> Reporter["reporter / profile<br/>报告与最终画像"]
    Reporter --> Storage["storage<br/>SQLite interview_memory"]
```

## 代码模块说明

- `app.py`：Streamlit 入口，负责页面状态和端到端编排。
- `src/document_loader.py`：解析 PDF / Word 简历。
- `src/structurer.py`：JD 和简历结构化抽取。
- `src/matcher.py`：JD-Resume 匹配分析。
- `src/config_parser.py`：解析用户自然语言面试要求。
- `src/role_builder.py`：生成面试官角色设定。
- `src/planner.py`：自我介绍后生成正式考察地图，并按 plan 大方向数量驱动面试推进。
- `src/probe_planner.py`：选择当前大方向，生成检索 query。
- `src/question_retriever.py`：SQLite FTS5 / BM25 题库检索。
- `src/question_composer.py`：生成上下文相关的具体问题。
- `src/interviewer.py`：串联方向选择、题库检索和问题生成。
- `src/evaluator.py`：单轮回答观察，不做评分。
- `src/flow_controller.py`：决定继续追问、切换方向或结束面试。
- `src/direction_scorer.py`：对大方向进行 1-4 档评分。
- `src/memory.py`：运行时面试记忆。
- `src/profile.py`：面试前简报和面试后候选人画像。
- `src/reporter.py`：生成最终可读面试报告。
- `src/storage.py`：SQLite 单表持久化。
- `src/llm_client.py`：LLM 兼容接口和 fallback 处理。

## Prompt 设计思路

本项目没有用一个大 Prompt 处理所有事情，而是按职责拆成多个小 Prompt：

- Structurer Prompt：只抽取事实字段，避免提前判断。
- Matcher Prompt：做 JD-Resume 对齐，输出匹配点、缺口和待验证假设。
- Planner Prompt：生成稳定考察方向，不提前固定每一轮问题。
- Question Composer Prompt：在固定大方向下，结合简历细节和题库参考生成当前问题。
- Evaluator Prompt：只观察单轮回答，输出是否追问、证据、缺失点和风险。
- Direction Scorer Prompt：汇总一个大方向下的多轮问答后统一评分。
- Reporter Prompt：把结构化结果转成招聘负责人能读懂的 Markdown 报告。

稳定性处理：

- 要求 LLM 输出 JSON。
- 使用 `extract_json` 从 Markdown 代码块或混杂文本中提取 JSON。
- 每个核心节点都有 fallback，未配置 API Key 时仍可演示主流程。
- 流程决策由 `FlowController` 基于结构化信号完成，避免完全依赖 LLM 随机判断。
- Question Composer 会校验题库问题和当前经历是否相关，禁止把简历/JD/当前方向中没有的概念硬塞进问题。

### 关键 Prompt 示例

Structurer 的核心约束：

```text
只抽取 JD/简历原文中存在的信息，不要补充常识、推测条件或创造新经历。
结构化层只输出事实字段，不输出风险判断。
缺失字段使用空数组或 unknown。
```

Matcher 的核心约束：

```text
不要输出匹配分，不要做最终录用判断。
将风险表述为“待验证假设”，例如个人贡献边界、项目真实性、指标口径。
结论必须服务于下一步面试应该验证什么。
```

Planner 的核心约束：

```text
不要生成固定总轮次。
正式 plan 必须结合 JD、简历、Matcher 和候选人自我介绍。
experience_probe_plan 针对项目/实习生成 2-3 个大方向。
技能和业务场景不单独成环节，而是融入项目/实习深挖方向中验证。
```

Question Composer 的核心约束：

```text
题库候选题只能作为参考角度，不能照搬。
如果题库问题中的概念没有出现在候选人经历、JD 或当前考察方向中，禁止写进最终问题。
最终问题必须是一段自然中文，不要把简历原文大段贴给候选人。
```

Direction Scorer 的核心约束：

```text
不要给每个小问题打分。
只在一个大方向结束后，汇总该方向下的多轮问答，给 1-4 档验证等级。
评分必须包含证据、缺失点、评语和下一步建议。
```

## 难点与解决方案

### 难点 1：不能让 LLM 直接“自由面试”

如果直接把 JD 和简历丢给一个聊天模型，问题会很容易发散，且难以解释为什么问这个问题。

解决方案：

- 先用 Structurer 把 JD 和简历变成稳定 JSON。
- 再用 Matcher 输出匹配点、缺口和待验证假设。
- 自我介绍后再生成正式 plan，让计划吸收候选人主动强调的经历。
- 后续问题都绑定到 plan 的大方向。

### 难点 2：题库检索可能检出不相关问题

例如候选人经历里只有 MCP 工具开发，题库却检出“Agent 长短期记忆”问题。如果直接融合，会出现不符合经历事实的问题。

解决方案：

- 题库只作为参考，不直接照抄。
- `question_composer.py` 会检查题库概念是否出现在当前经历、JD 或考察方向中。
- 如果概念不相关，则回退为基于经历事实的问题。

### 难点 3：面试轮次不能固定

固定 8 轮不符合真实面试。不同候选人的项目数量、技能数量和回答质量都不同。

解决方案：

- 删除固定 `max_rounds` 截断。
- 轮次由 `experience_probe_plan` 的大方向数量决定。
- 如果回答不充分，Flow Controller 允许在当前方向继续追问。
- plan 方向走完后结束面试。

### 难点 4：评分粒度容易过细

如果每个动态小问题都打分，评分会受提问措辞影响，噪声较大。

解决方案：

- 小问题只负责采证。
- Evaluation Agent 只做单轮观察，不打分。
- Direction Scoring Agent 在一个大方向结束后汇总多轮问答，统一给 1-4 档评分。

## 安装与启动

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

`.env` 示例：

```bash
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
OPENAI_TIMEOUT=180
OPENAI_MAX_RETRIES=0

OCR_MODEL=PaddlePaddle/PaddleOCR-VL-1.5
OCR_TIMEOUT=180

BROWSER_TTS_ENABLED=false
XINGYUN_AVATAR_ENABLED=false
```

如果不配置 `OPENAI_API_KEY`，系统会进入本地 fallback 模式，可以演示主流程，但真实提取和回答质量会低于接入模型后的效果。

## 演示步骤

1. 启动 Streamlit。
2. 上传候选人简历 PDF / Word。
3. 粘贴 JD 文本。
4. 可选填写面试官风格要求。
5. 点击开始面试。
6. 第一轮候选人完成自我介绍。
7. 系统结合自我介绍生成正式面试 plan。
8. 候选人用文字回答后续问题。
9. 系统根据回答质量选择继续追问或切换方向。
10. 面试结束后展示最终 Markdown 报告。

建议演示视频覆盖：

- JD + 简历输入
- 结构化结果
- Matcher 分析
- 自我介绍后生成的 Planner 考察方向
- 至少两轮动态追问
- 一个大方向评分
- 最终可读报告

## 当前边界与后续演进

当前 MVP 默认保存最近一次 `latest` session，适合笔试 Demo。

后续可以扩展：

- 支持多候选人、多岗位、多轮面试 session。
- 题库检索升级为 BM25 + Embedding Hybrid Retrieval + Reranker。
- 将方向评分 rubric 做成可配置能力模型。
- 把 `final_profile_json` 接入下一轮面试，形成跨轮候选人画像。
- 接入语音/TTS/数字人作为展示层，但不改变核心面试链路。
