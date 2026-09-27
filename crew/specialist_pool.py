"""
Display metadata for the fixed specialist pool. The keys here MUST exactly
match the specialist keys in crew/config/agents.yaml and the list given to
the domain_router agent in crew/config/tasks.yaml - this is the single
source of truth the router is allowed to choose from.
"""

SPECIALIST_POOL = {
    "mechanical_specialist": {"icon": "\U0001F527", "label": "Mechanical Engineering Specialist"},
    "manufacturing_specialist": {"icon": "\U0001F3ED", "label": "Manufacturing Specialist"},
    "electrical_specialist": {"icon": "\u26A1", "label": "Electrical/Electronics Specialist"},
    "civil_specialist": {"icon": "\U0001F3D7\uFE0F", "label": "Civil Engineering Specialist"},
    "chemical_specialist": {"icon": "\U0001F9EA", "label": "Chemical Engineering Specialist"},
    "materials_specialist": {"icon": "\U0001F52C", "label": "Materials Science Specialist"},
    "biotech_specialist": {"icon": "\U0001F9EC", "label": "Biotechnology Specialist"},
    "software_specialist": {"icon": "\U0001F4BB", "label": "Software Engineering Specialist"},
    "data_ai_specialist": {"icon": "\U0001F4CA", "label": "Data/AI Specialist"},
    "quality_ops_specialist": {"icon": "\u2705", "label": "Quality, Reliability & Operations Specialist"},
}

FIXED_ROLE_ICONS = {
    "problem_intake": "\U0001F9E0",
    "domain_router": "\U0001F9ED",
    "research_agent": "\U0001F50E",
    "critical_reviewer": "\u26A0\uFE0F",
}
