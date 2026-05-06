"""Skills Index — Mapping of agents to their relevant marketing skills.

This module provides a declarative mapping of which marketing skills
each sub-agent should load for different tasks. The skills are
loaded on-demand via SkillLoaderTool, not preloaded into context.
"""

# Agent to skills mapping — each agent should load these when working on related tasks
AGENT_SKILLS = {
    "seogeo": [
        "ai-seo",          # AI search engine optimization
        "content-strategy", # Content planning and architecture
        "competitor-profiling",  # Competitor analysis
        "seo-audit",       # Technical SEO auditing
        "programmatic-seo", # Automated SEO at scale
    ],
    "social_manager": [
        "social-content",   # Social media content creation
        "copywriting",      # Engaging copy for social
        "launch-strategy",  # Go-to-market for campaigns
        "community-marketing",  # Building engaged communities
        "video",            # Video content strategy
    ],
    "copywriter": [
        "copywriting",      # Core copywriting principles
        "copy-editing",     # Editing and refinement
        "ab-test-setup",    # A/B testing copy variants
        "lead-magnets",     # Lead generation content
        "ad-creative",      # Advertising copy
    ],
    "cmo": [
        # CMO has overview access to all skills for strategic decisions
        "content-strategy",
        "launch-strategy",
        "competitor-profiling",
        "marketing-psychology",
        "analytics-tracking",
    ],
}

# Skill categories for reference
SKILL_CATEGORIES = {
    "SEO & Discovery": ["ai-seo", "seo-audit", "programmatic-seo", "competitor-profiling", "competitor-alternatives", "schema-markup", "directory-submissions", "aso-audit"],
    "Content & Copy": ["content-strategy", "copywriting", "copy-editing", "video", "image", "free-tool-strategy"],
    "Social & Community": ["social-content", "community-marketing", "launch-strategy", "referral-program"],
    "Conversion & Growth": ["ab-test-setup", "lead-magnets", "onboarding-cro", "signup-flow-cro", "page-cro", "popup-cro", "form-cro", "paywall-upgrade-cro"],
    "Channels & Campaigns": ["ad-creative", "paid-ads", "email-sequence", "cold-email", "product-marketing-context"],
    "Analytics & Strategy": ["analytics-tracking", "customer-research", "marketing-ideas", "marketing-psychology", "pricing-strategy", "revops", "sales-enablement", "site-architecture", "churn-prevention"],
}


def get_skills_for_agent(agent_name: str) -> list:
    """Get the list of skills for a given agent name."""
    return AGENT_SKILLS.get(agent_name, [])


def get_skill_description(skill_name: str) -> str:
    """Get a human-readable description of a skill category."""
    for category, skills in SKILL_CATEGORIES.items():
        if skill_name in skills:
            return f"{category}: {skill_name}"
    return skill_name
