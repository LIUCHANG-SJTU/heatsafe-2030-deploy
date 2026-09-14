from __future__ import annotations

from dataclasses import dataclass

from .models import ActionFamily


ACTION_CATALOG_VERSION = "M5C_ACTION_CATALOG_V1"

ACTION_FAMILY_STABLE_ORDER = {
    ActionFamily.HEAT_EXPOSURE_MITIGATION: 0,
    ActionFamily.POPULATION_EXPOSURE_MANAGEMENT: 1,
    ActionFamily.VULNERABLE_POPULATION_PROTECTION: 2,
    ActionFamily.ADAPTIVE_CAPACITY_ENHANCEMENT: 3,
}


@dataclass(frozen=True)
class ActionCatalogEntry:
    title_zh: str
    title_en: str
    actions_zh: tuple[str, ...]
    actions_en: tuple[str, ...]
    guidance_ids: tuple[str, ...]


ACTION_CATALOG = {
    ActionFamily.HEAT_EXPOSURE_MITIGATION: ActionCatalogEntry(
        title_zh="热暴露缓解",
        title_en="Heat Exposure Mitigation",
        actions_zh=(
            "优先评估步行与公共活动空间的遮阴条件",
            "在高温时段加强重点热区的公共空间热暴露管理",
            "评估被动降温与低吸热表面的适用机会",
        ),
        actions_en=(
            "Prioritize assessment of shade in walking and public activity spaces",
            "Strengthen hot-period public-space heat exposure management",
            "Assess suitable passive-cooling and lower-heat-absorption options",
        ),
        guidance_ids=("WHO_HHAP_2026_REDUCE_EXPOSURE", "UNHABITAT_UHM_2025_PASSIVE_COOLING"),
    ),
    ActionFamily.POPULATION_EXPOSURE_MANAGEMENT: ActionCatalogEntry(
        title_zh="人口暴露管理",
        title_en="Population Exposure Management",
        actions_zh=(
            "优先评估高人口暴露区域的避暑服务承载能力",
            "加强高温信息与公共服务的覆盖和触达",
            "规划高温重点时段的现场服务与人流管理",
        ),
        actions_en=(
            "Prioritize assessment of cooling-service capacity in highly exposed areas",
            "Strengthen the reach of heat information and public services",
            "Plan on-site services and crowd management for priority hot periods",
        ),
        guidance_ids=("WHO_HHAP_2026_COMMUNICATION", "UNHABITAT_UHM_2025_SUSTAINABLE_COOLING"),
    ),
    ActionFamily.VULNERABLE_POPULATION_PROTECTION: ActionCatalogEntry(
        title_zh="脆弱人群保护",
        title_en="Vulnerable Population Protection",
        actions_zh=(
            "优先考虑老年人和儿童等重点人群的高温信息触达",
            "加强社区主动联系与照护协同机制",
            "评估重点人群获得避暑空间与健康服务的便利性",
        ),
        actions_en=(
            "Prioritize heat-information outreach for older adults, children, and other priority groups",
            "Strengthen proactive community contact and care coordination",
            "Assess priority groups' access to cooling spaces and health services",
        ),
        guidance_ids=("WHO_HHAP_2026_RISK_GROUPS", "WHO_HHAP_2026_COMMUNICATION"),
    ),
    ActionFamily.ADAPTIVE_CAPACITY_ENHANCEMENT: ActionCatalogEntry(
        title_zh="适应能力提升",
        title_en="Adaptive Capacity Enhancement",
        actions_zh=(
            "优先评估绿荫、树冠与连续遮阴条件",
            "评估绿地和自然基础降温措施的适用机会",
            "规划步行空间与公共服务节点的热环境改善",
        ),
        actions_en=(
            "Prioritize assessment of green shade, tree canopy, and continuous shade",
            "Assess suitable green-infrastructure and nature-based cooling opportunities",
            "Plan thermal-environment improvements for walking routes and public-service nodes",
        ),
        guidance_ids=("UNHABITAT_UHM_2025_GREEN_INFRA", "WHO_HHAP_2026_REDUCE_EXPOSURE"),
    ),
}
