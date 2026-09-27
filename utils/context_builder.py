def build_problem_context_text(confirmed: dict) -> str:
    """
    Turns the human-confirmed Checkpoint 1 data into a single plain-text block
    that gets substituted into every downstream task description. Keeping
    this in one place means Checkpoint 1 edits automatically flow into every
    specialist's prompt without touching the crew-building code.
    """
    objectives = confirmed.get("objectives", []) or []
    constraints = confirmed.get("constraints", []) or []
    assumptions = confirmed.get("assumptions", []) or []
    missing_information = confirmed.get("missing_information", []) or []
    domains = confirmed.get("domains", []) or []

    def bullet_list(items):
        return "\n".join(f"- {item}" for item in items) if items else "- (none stated)"

    return (
        f"Problem summary (human-confirmed):\n{confirmed.get('problem_summary', '')}\n\n"
        f"Relevant domains: {', '.join(domains) if domains else '(none specified)'}\n\n"
        f"Objectives:\n{bullet_list(objectives)}\n\n"
        f"Constraints:\n{bullet_list(constraints)}\n\n"
        f"Assumptions:\n{bullet_list(assumptions)}\n\n"
        f"Known missing information:\n{bullet_list(missing_information)}"
    )
