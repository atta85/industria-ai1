"""
The final report is assembled by plain Python from data already produced and
already shown to the human at Checkpoint 1 and Checkpoint 2 - it is NOT a
fresh LLM call. This is deliberate: the "final" step should be a
deterministic, auditable transcription of what the human already reviewed
and approved, not one more place where a model could quietly change the
content after the human signed off on it.
"""

from datetime import datetime


def build_final_report(
    original_problem_statement: str,
    confirmed: dict,
    investigation: dict,
    human_decision: str,
    human_feedback_history: list,
) -> dict:
    return {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "problem_statement": original_problem_statement,
        "human_confirmed_interpretation": confirmed.get("problem_summary", ""),
        "relevant_domains": confirmed.get("domains", []),
        "agents_consulted": investigation.get("agents_involved", []),
        "evidence_collected": investigation.get("evidence", []),
        "tool_usage": investigation.get("tool_usage", []),
        "evidence_available": investigation.get("evidence_available", False),
        "evidence_notes": investigation.get("evidence_notes", ""),
        "specialist_findings": investigation.get("specialist_results", []),
        "critical_review": investigation.get("critical_review", {}),
        "human_feedback_history": human_feedback_history,
        "human_verification_status": human_decision,
        "warnings": _build_warnings(confirmed, investigation),
    }


def _build_warnings(confirmed: dict, investigation: dict) -> list:
    warnings = []
    if not investigation.get("evidence_available", False):
        warnings.append(
            "No external web evidence was available for this analysis. "
            "Root causes and solutions below are agent inference, not "
            "independently verified fact - further verification is recommended."
        )
    if confirmed.get("missing_information"):
        warnings.append(
            "The AI identified missing information that was not resolved "
            "before analysis proceeded - see 'Known missing information'."
        )
    warnings.append(
        "This is a decision-support report, not a substitute for a qualified "
        "professional. For safety-critical, medical, legal, or financial "
        "matters, independent expert verification is strongly recommended."
    )
    return warnings


def report_to_markdown(report: dict) -> str:
    lines = []
    lines.append("# Verified Decision-Support Report")
    lines.append(f"*Generated {report['generated_at_utc']} — Industria-AI*\n")

    lines.append("## 1. Problem Statement")
    lines.append(report["problem_statement"] or "(not provided)")

    lines.append("\n## 2. Human-Confirmed Interpretation")
    lines.append(report["human_confirmed_interpretation"] or "(not provided)")

    lines.append("\n## 3. Relevant Domains")
    for d in report["relevant_domains"] or ["(none)"]:
        lines.append(f"- {d}")

    lines.append("\n## 4. Agents Consulted")
    for a in report["agents_consulted"] or ["(none)"]:
        lines.append(f"- {a}")

    lines.append("\n## 5. Evidence Collected")
    if report["evidence_available"] and report["evidence_collected"]:
        for e in report["evidence_collected"]:
            title = e.get("source_title", "Untitled source")
            url = e.get("source_url", "")
            finding = e.get("finding", "")
            lines.append(f"- **{finding}** — [{title}]({url})" if url else f"- **{finding}** — {title}")
    else:
        lines.append("_No external evidence was available. All findings below are agent inference._")
    if report.get("evidence_notes"):
        lines.append(f"\n*Research notes: {report['evidence_notes']}*")

    lines.append("\n## Tools Used by Agents")
    if report.get("tool_usage"):
        for t in report["tool_usage"]:
            lines.append(f"- `{t.get('time', '')}` **{t.get('agent', '')}** used `{t.get('tool', '')}` on \"{t.get('input', '')}\" - {t.get('status', '')} ({t.get('detail', '')})")
    else:
        lines.append("_No tools were called during this analysis._")

    lines.append("\n## 6-9. Specialist Findings (Root Causes, Alternatives, Solutions, Risks)")
    for s in report["specialist_findings"]:
        lines.append(f"\n### {s.get('specialist', s.get('specialist_key', 'Specialist'))}")
        lines.append(f"- **Confidence:** {s.get('confidence', 'not stated')}")
        lines.append("- **Possible root causes:**")
        for c in s.get("possible_root_causes", []):
            lines.append(f"  - {c}")
        if s.get("cause_basis"):
            lines.append("- **Evidence vs. inference:**")
            for cb in s.get("cause_basis", []):
                lines.append(f"  - {cb}")
        lines.append("- **Proposed solutions:**")
        for sol in s.get("proposed_solutions", []):
            lines.append(f"  - {sol}")
        lines.append("- **Risks of proposed solutions:**")
        for r in s.get("risks_of_proposed_solutions", []):
            lines.append(f"  - {r}")

    cr = report.get("critical_review", {})
    lines.append("\n## 10. Critical Review")
    lines.append("**Critical findings:**")
    for f in cr.get("critical_findings", []):
        lines.append(f"- {f}")
    lines.append("\n**Alternative explanations considered:**")
    for a in cr.get("alternative_explanations", []):
        lines.append(f"- {a}")
    lines.append("\n**Unresolved uncertainty:**")
    for u in cr.get("unresolved_uncertainty", []):
        lines.append(f"- {u}")
    if cr.get("overall_confidence_assessment"):
        lines.append(f"\n**Overall confidence assessment:** {cr['overall_confidence_assessment']}")

    lines.append("\n## 11. Human Feedback History")
    if report["human_feedback_history"]:
        for entry in report["human_feedback_history"]:
            lines.append(f"- [{entry.get('timestamp', '')}] **{entry.get('decision', '')}** — {entry.get('detail', '')}")
    else:
        lines.append("_No revisions were requested._")

    lines.append("\n## 12. Human Verification Status")
    lines.append(f"**{report['human_verification_status']}**")

    lines.append("\n## 13. Important Warnings & Uncertainties")
    for w in report["warnings"]:
        lines.append(f"- ⚠️ {w}")

    lines.append(
        "\n---\n*Based on the available evidence and agent analysis above. "
        "Further verification by a qualified human expert is recommended "
        "before acting on any proposed solution.*"
    )

    return "\n".join(lines)
