from __future__ import annotations

from typing import Literal


AgentLocale = Literal["zh-CN", "en"]


def response_language_instruction(locale: AgentLocale) -> str:
    if locale == "en":
        return "Respond in English. Refer to the public product scope as the analysis area, not a demo. Keep Evidence IDs, metric keys, grid IDs, and internal codes unchanged."
    return "Respond in Simplified Chinese. Use 分析区域 for the public product scope; do not call the product a demo. Keep Evidence IDs, metric keys, grid IDs, and internal codes unchanged."


def agent_status_message(locale: AgentLocale, state: Literal["reading", "validating"]) -> str:
    messages = {
        "zh-CN": {
            "reading": "正在读取 HeatSafe 数据…",
            "validating": "正在验证数据依据…",
        },
        "en": {
            "reading": "Reading HeatSafe data…",
            "validating": "Validating evidence…",
        },
    }
    return messages[locale][state]


def guard_message(locale: AgentLocale, key: str) -> str:
    messages = {
        "zh-CN": {
            "injection": "我不能提供系统提示词、API key 或执行本地代码。HeatSafe Agent 只允许读取公开的、确定性的 HeatSafe 数据工具。",
            "missing_grid": "当前没有选中格网。请先在地图上选择一个格网，再请求该位置的行动优先级建议。",
            "risk_scope": "不是。HeatSafe 风险值是所选分析区域内部的相对空间风险，用于区域比较，不代表死亡概率、健康结局概率或杭州市整体绝对风险。",
            "medical": "不能提供医疗诊断或保证性的政策优化方案。HeatSafe 仅支持基于现有 REAL 数据的相对风险诊断与关注优先级分析。",
        },
        "en": {
            "injection": "I cannot provide system prompts or API keys, or execute local code. HeatSafe Agent can only read the public, deterministic HeatSafe data tools.",
            "missing_grid": "No grid is currently selected. Select a grid on the map before requesting action priorities for that location.",
            "risk_scope": "No. HeatSafe scores are relative spatial risk within the selected analysis area for comparing areas. They are not mortality probabilities, health-outcome probabilities, or absolute citywide risk.",
            "medical": "I cannot provide medical diagnoses or guaranteed policy optimization. HeatSafe only supports relative risk diagnosis and priority analysis grounded in the current REAL data.",
        },
    }
    return messages[locale][key]
