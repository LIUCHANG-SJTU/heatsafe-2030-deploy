from __future__ import annotations

from .models import ActionGuidanceRef


ACTION_GUIDANCE_VERSION = "M5C_ACTION_GUIDANCE_V1"

WHO_URL = "https://www.who.int/europe/publications/i/item/9789289062930"
UNHABITAT_URL = "https://unhabitat.org/handbook-on-urban-heat-management-in-the-global-south"


def _guidance(
    guidance_id: str,
    organization_zh: str,
    organization_en: str,
    title_zh: str,
    title_en: str,
    year: int,
    section_zh: str,
    section_en: str,
    url: str,
) -> ActionGuidanceRef:
    return ActionGuidanceRef(
        guidance_id=guidance_id,
        organization_zh=organization_zh,
        organization_en=organization_en,
        title_zh=title_zh,
        title_en=title_en,
        year=year,
        section_zh=section_zh,
        section_en=section_en,
        url=url,
    )


ACTION_GUIDANCE_REGISTRY = {
    "WHO_HHAP_2026_REDUCE_EXPOSURE": _guidance(
        "WHO_HHAP_2026_REDUCE_EXPOSURE",
        "世界卫生组织欧洲区域办事处",
        "World Health Organization Regional Office for Europe",
        "高温-健康行动计划：指南（第二版）",
        "Heat-health action plans: guidance, second edition",
        2026,
        "减少室内外高温暴露",
        "Reduction in indoor and outdoor heat exposure",
        WHO_URL,
    ),
    "WHO_HHAP_2026_RISK_GROUPS": _guidance(
        "WHO_HHAP_2026_RISK_GROUPS",
        "世界卫生组织欧洲区域办事处",
        "World Health Organization Regional Office for Europe",
        "高温-健康行动计划：指南（第二版）",
        "Heat-health action plans: guidance, second edition",
        2026,
        "重点照护脆弱人群",
        "Special care for vulnerable population groups",
        WHO_URL,
    ),
    "WHO_HHAP_2026_COMMUNICATION": _guidance(
        "WHO_HHAP_2026_COMMUNICATION",
        "世界卫生组织欧洲区域办事处",
        "World Health Organization Regional Office for Europe",
        "高温-健康行动计划：指南（第二版）",
        "Heat-health action plans: guidance, second edition",
        2026,
        "高温相关信息与沟通",
        "Heat-related information and communication",
        WHO_URL,
    ),
    "UNHABITAT_UHM_2025_PASSIVE_COOLING": _guidance(
        "UNHABITAT_UHM_2025_PASSIVE_COOLING",
        "联合国人居署 / 世界银行 / 联合国环境署",
        "UN-Habitat / World Bank / UNEP",
        "全球南方城市高温管理手册",
        "Handbook on Urban Heat Management in the Global South",
        2025,
        "被动降温与热韧性公共空间",
        "Passive cooling and heat-resilient public space",
        UNHABITAT_URL,
    ),
    "UNHABITAT_UHM_2025_GREEN_INFRA": _guidance(
        "UNHABITAT_UHM_2025_GREEN_INFRA",
        "联合国人居署 / 世界银行 / 联合国环境署",
        "UN-Habitat / World Bank / UNEP",
        "全球南方城市高温管理手册",
        "Handbook on Urban Heat Management in the Global South",
        2025,
        "绿蓝基础设施",
        "Green and blue infrastructure",
        UNHABITAT_URL,
    ),
    "UNHABITAT_UHM_2025_SUSTAINABLE_COOLING": _guidance(
        "UNHABITAT_UHM_2025_SUSTAINABLE_COOLING",
        "联合国人居署 / 世界银行 / 联合国环境署",
        "UN-Habitat / World Bank / UNEP",
        "全球南方城市高温管理手册",
        "Handbook on Urban Heat Management in the Global South",
        2025,
        "可持续降温与城市高温治理",
        "Sustainable cooling and urban heat governance",
        UNHABITAT_URL,
    ),
}
