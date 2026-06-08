DEFAULT_INTERVIEW_CONFIG = {
    "interviewer": {
        "role": "技术面试官",
        "style": "严谨追问",
        "tone": "专业、直接、尊重候选人，关注项目真实性和技术细节",
        "focus_areas": ["项目真实性", "个人贡献", "技术深度", "工程落地", "问题解决"],
        "follow_up_intensity": "medium",
        "scoring_strictness": "standard",
    },
    "interview_flow": {
        "total_duration_minutes": 68,
        "target_rounds": 6,
        "demo_rounds": 6,
        "min_rounds": 4,
        "max_rounds": 10,
        "stages": [
            {
                "id": "self_intro",
                "name": "3分钟自我介绍",
                "duration_minutes": 3,
                "demo_rounds": 1,
                "goal": "观察候选人的表达结构、职业主线和岗位相关经历。",
            },
            {
                "id": "resume_deep_dive",
                "name": "简历深挖",
                "duration_minutes": 40,
                "demo_rounds": 3,
                "goal": "深挖实习、项目、论文、竞赛，验证真实性、个人贡献和技术细节。",
            },
            {
                "id": "tech_stack_scenario",
                "name": "技术栈与场景题",
                "duration_minutes": 15,
                "demo_rounds": 1,
                "goal": "围绕 JD 与简历交集技术栈，考察基础知识、场景迁移和工程理解。",
            },
        ],
    },
}
