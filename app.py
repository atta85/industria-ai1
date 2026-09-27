import streamlit as st

from crew.intake_crew import run_intake_crew
from crew.investigation_crew import run_investigation_crew
from crew.specialist_pool import FIXED_ROLE_ICONS, SPECIALIST_POOL
from utils.context_builder import build_problem_context_text
from utils.litellm_patch import apply_groq_litellm_patch
from utils.report_builder import build_final_report, report_to_markdown
from utils.retry import run_with_retry
from utils.state import init_state, log_audit, reset_state

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Industria-AI", page_icon="\U0001F3ED", layout="wide")

CUSTOM_CSS = """
<style>
.industria-hero {
    background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
    padding: 1.6rem 2rem;
    border-radius: 14px;
    color: #f9fafb;
    margin-bottom: 1.2rem;
}
.industria-hero h1 { margin-bottom: 0.2rem; }
.industria-hero p { color: #d1d5db; margin: 0; }
.industria-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 1rem;
}
.industria-warning {
    background: #fff7ed;
    border-left: 4px solid #f59e0b;
    padding: 0.8rem 1rem;
    border-radius: 8px;
    margin-bottom: 0.8rem;
}
.industria-badge {
    display: inline-block;
    background: #eef2ff;
    color: #3730a3;
    border-radius: 999px;
    padding: 0.15rem 0.7rem;
    font-size: 0.85rem;
    margin: 0.1rem 0.2rem 0.1rem 0;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

apply_groq_litellm_patch()
init_state()

# ---------------------------------------------------------------------------
# Secrets / LLM setup
# ---------------------------------------------------------------------------
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY")
SERPER_API_KEY = st.secrets.get("SERPER_API_KEY")

if not GROQ_API_KEY:
    st.error(
        "**GROQ_API_KEY is missing.** Add it under your app's Settings → "
        "Secrets on Streamlit Cloud (or in `.streamlit/secrets.toml` locally), "
        "then reload this app."
    )
    st.stop()


@st.cache_resource(show_spinner=False)
def get_llms(api_key: str):
    # Imported here so the cached resource is rebuilt if the key changes.
    from crewai import LLM

    heavy = LLM(model="groq/openai/gpt-oss-120b", api_key=api_key, temperature=0.4)
    light = LLM(model="groq/openai/gpt-oss-20b", api_key=api_key, temperature=0.3)
    return heavy, light


llm_heavy, llm_light = get_llms(GROQ_API_KEY)

DEMO_SCENARIOS = {
    "\U0001F3ED Manufacturing": "A production line making injection-molded plastic housings has seen dimensional defects (parts out of tolerance) increase from about 2% to 11% over the past three weeks. No obvious change to the mold or operators was made.",
    "\U0001F4BB Software": "Our web application became noticeably slower for users after we deployed an update two days ago. Average page load time went from ~400ms to over 2 seconds, and it's affecting all pages, not just the ones we changed.",
    "\U0001F9EC Biotechnology": "A fermentation-based bioprocess is producing inconsistent product yield between batches - some batches hit target yield and others fall 30-40% short, even though the recipe and equipment are supposedly identical.",
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### \U0001F3ED Industria-AI")
    st.caption("Human-in-the-loop multi-agent decision support")

    st.markdown("---")
    st.markdown("**Agent Activity**")
    stage = st.session_state.stage
    if stage in ("input",):
        st.caption("Idle — waiting for a problem.")
    if stage in ("checkpoint1",):
        st.markdown(f"{FIXED_ROLE_ICONS['problem_intake']} Problem Intake — done")
        st.markdown(f"{FIXED_ROLE_ICONS['domain_router']} Domain Router — done")
    if stage in ("checkpoint2", "final"):
        st.markdown(f"{FIXED_ROLE_ICONS['problem_intake']} Problem Intake — done")
        st.markdown(f"{FIXED_ROLE_ICONS['domain_router']} Domain Router — done")
        st.markdown(f"{FIXED_ROLE_ICONS['research_agent']} Research Agent — done")
        for key in (st.session_state.confirmed or {}).get("selected_specialists", []):
            info = SPECIALIST_POOL.get(key, {})
            st.markdown(f"{info.get('icon', '')} {info.get('label', key)} — done")
        st.markdown(f"{FIXED_ROLE_ICONS['critical_reviewer']} Critical Reviewer — done")

    st.markdown("---")
    if not SERPER_API_KEY:
        st.caption("\u26A0\uFE0F No SERPER_API_KEY set — research will run in degraded (no-evidence) mode.")
    else:
        st.caption("\u2705 Web search evidence enabled.")

    st.markdown("---")
    if st.button("\U0001F504 Start New Problem", use_container_width=True):
        reset_state()
        st.rerun()

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="industria-hero">
        <h1>\U0001F3ED Industria-AI</h1>
        <p>A human-in-the-loop multi-agent AI system for analyzing complex real-world problems.
        AI analyzes. AI cross-checks. Human verifies. AI finalizes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Audit trail (always available, collapsed)
# ---------------------------------------------------------------------------
def render_audit_trail():
    with st.expander("\U0001F4CB Human Audit Trail", expanded=False):
        if not st.session_state.audit_trail:
            st.caption("No events logged yet.")
        for entry in st.session_state.audit_trail:
            st.markdown(f"`{entry['timestamp']}` **{entry['event']}** {entry['detail']}")


# ---------------------------------------------------------------------------
# STAGE: input
# ---------------------------------------------------------------------------
if st.session_state.stage == "input":
    st.markdown("#### Try a demo scenario, or describe your own problem below")
    cols = st.columns(3)
    for col, (label, text) in zip(cols, DEMO_SCENARIOS.items()):
        if col.button(label, use_container_width=True):
            st.session_state.prefill_problem = text
            st.rerun()

    st.markdown("<div class='industria-card'>", unsafe_allow_html=True)
    problem_statement = st.text_area(
        "Describe your problem",
        value=st.session_state.prefill_problem,
        height=140,
        placeholder="e.g. A production line is experiencing increasing dimensional defects...",
    )

    with st.expander("Optional details (industry, objective, constraints, data, desired outcome)"):
        industry = st.text_input("Industry / domain")
        objective = st.text_input("Objective")
        constraints_input = st.text_input("Constraints")
        available_data = st.text_input("Available data")
        desired_outcome = st.text_input("Desired outcome")

    analyze_clicked = st.button("\U0001F50D Analyze Problem", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if analyze_clicked:
        if not problem_statement or not problem_statement.strip():
            st.warning("Please describe a problem before analyzing.")
        else:
            with st.spinner("Problem Intake & Domain Router agents are analyzing your problem..."):
                try:
                    result = run_with_retry(
                        run_intake_crew,
                        problem_statement=problem_statement,
                        industry=industry,
                        objective=objective,
                        constraints=constraints_input,
                        available_data=available_data,
                        desired_outcome=desired_outcome,
                        llm_light=llm_light,
                    )
                    st.session_state.problem_statement = problem_statement
                    st.session_state.intake_result = result
                    st.session_state.confirmed = dict(result)  # editable copy for Checkpoint 1
                    log_audit("Problem submitted", f"— {problem_statement[:80]}...")
                    log_audit("Intake & routing complete", f"— domains: {', '.join(result.get('domains', []))}")
                    st.session_state.stage = "checkpoint1"
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(
                        "Something went wrong while analyzing your problem. "
                        "You can try again below, or start over from the sidebar."
                    )
                    with st.expander("Technical details"):
                        st.code(str(exc))

    render_audit_trail()

# ---------------------------------------------------------------------------
# STAGE: checkpoint1 — AI Understanding of Your Problem
# ---------------------------------------------------------------------------
elif st.session_state.stage == "checkpoint1":
    st.markdown("### \U0001F9E0 Checkpoint 1 — AI Understanding of Your Problem")
    st.caption("Review the AI's interpretation before any deeper analysis runs. Edit anything that's wrong.")

    c = st.session_state.confirmed
    if c.get("intake_parse_error") or c.get("routing_parse_error"):
        st.markdown(
            "<div class='industria-warning'>\u26A0\uFE0F One of the agents did not return clean structured "
            "output. Fields below may be incomplete — please review carefully.</div>",
            unsafe_allow_html=True,
        )

    with st.container():
        st.markdown("<div class='industria-card'>", unsafe_allow_html=True)
        problem_summary = st.text_area("Problem summary", value=c.get("problem_summary", ""), height=100)
        domains_text = st.text_area(
            "Relevant domains (one per line)", value="\n".join(c.get("domains", [])), height=70
        )
        objectives_text = st.text_area(
            "Objectives (one per line)", value="\n".join(c.get("objectives", [])), height=70
        )
        constraints_text = st.text_area(
            "Constraints (one per line)", value="\n".join(c.get("constraints", [])), height=70
        )
        assumptions_text = st.text_area(
            "Assumptions (one per line)", value="\n".join(c.get("assumptions", [])), height=70
        )
        missing_text = st.text_area(
            "Missing information (one per line)",
            value="\n".join(c.get("missing_information", [])),
            height=70,
        )

        st.markdown("**Specialists the AI selected:**")
        selected_display = [
            f"{SPECIALIST_POOL.get(k, {}).get('icon', '')} {SPECIALIST_POOL.get(k, {}).get('label', k)}"
            for k in c.get("selected_specialists", [])
        ]
        st.markdown(
            " ".join(f"<span class='industria-badge'>{s}</span>" for s in selected_display) or "_(none selected)_",
            unsafe_allow_html=True,
        )
        if c.get("routing_rationale"):
            st.caption(f"Why: {c['routing_rationale']}")
        st.markdown("</div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    confirm_clicked = col1.button("\u2713 Confirm (use AI's original interpretation)", use_container_width=True)
    modify_clicked = col2.button("\u270F Modify (use my edits above)", use_container_width=True)
    stop_clicked = col3.button("\u26D4 Stop Analysis", use_container_width=True)

    def _lines_to_list(text):
        return [line.strip() for line in text.splitlines() if line.strip()]

    if confirm_clicked or modify_clicked:
        if modify_clicked:
            st.session_state.confirmed.update(
                {
                    "problem_summary": problem_summary,
                    "domains": _lines_to_list(domains_text),
                    "objectives": _lines_to_list(objectives_text),
                    "constraints": _lines_to_list(constraints_text),
                    "assumptions": _lines_to_list(assumptions_text),
                    "missing_information": _lines_to_list(missing_text),
                }
            )
            log_audit("Human modified problem understanding", "— edits applied before analysis")
        else:
            log_audit("Human confirmed problem understanding", "— proceeding with AI's original interpretation")

        confirmed_context_text = build_problem_context_text(st.session_state.confirmed)
        selected = st.session_state.confirmed.get("selected_specialists", [])

        with st.spinner(
            "Research Agent, specialists, and Critical Reviewer are investigating this problem... "
            "this can take a minute or two."
        ):
            try:
                investigation = run_with_retry(
                    run_investigation_crew,
                    confirmed_context_text=confirmed_context_text,
                    selected_specialist_keys=selected,
                    llm_heavy=llm_heavy,
                    llm_light=llm_light,
                )
                st.session_state.investigation_result = investigation
                log_audit("Investigation complete", f"— {len(selected)} specialist(s) + research + critical review")
                st.session_state.stage = "checkpoint2"
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(
                    "Something went wrong during the investigation. "
                    "You can try Confirm/Modify again, or start over from the sidebar."
                )
                with st.expander("Technical details"):
                    st.code(str(exc))

    if stop_clicked:
        log_audit("Human stopped analysis", "— at Checkpoint 1 (problem understanding)")
        st.session_state.stage = "stopped"
        st.rerun()

    render_audit_trail()

# ---------------------------------------------------------------------------
# STAGE: checkpoint2 — AI-Proposed Solution
# ---------------------------------------------------------------------------
elif st.session_state.stage == "checkpoint2":
    st.markdown("### \U0001F4CA Checkpoint 2 — AI-Proposed Solution")
    inv = st.session_state.investigation_result
    confirmed = st.session_state.confirmed

    st.markdown("<div class='industria-card'>", unsafe_allow_html=True)
    st.markdown(f"**Problem interpretation:** {confirmed.get('problem_summary', '')}")
    st.markdown(f"**Relevant domains:** {', '.join(confirmed.get('domains', [])) or 'n/a'}")
    st.markdown("**Agents involved:**")
    st.markdown(
        " ".join(f"<span class='industria-badge'>{a}</span>" for a in inv.get("agents_involved", [])),
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='industria-card'>", unsafe_allow_html=True)
    st.markdown("#### \U0001F50E Evidence Gathered")
    if inv.get("evidence_available") and inv.get("evidence"):
        for e in inv["evidence"]:
            url = e.get("source_url", "")
            title = e.get("source_title", "Source")
            finding = e.get("finding", "")
            if url:
                st.markdown(f"- **{finding}** — [{title}]({url})")
            else:
                st.markdown(f"- **{finding}** — {title}")
    else:
        st.markdown(
            "<div class='industria-warning'>\u26A0\uFE0F No external evidence was available for this "
            "analysis (web search unavailable or returned nothing). Findings below are agent "
            "inference, not independently verified.</div>",
            unsafe_allow_html=True,
        )
    if inv.get("evidence_notes"):
        st.caption(inv["evidence_notes"])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("#### \U0001F9E9 Specialist Findings")
    for s in inv.get("specialist_results", []):
        title = f"{s.get('specialist_icon', '')} {s.get('specialist', s.get('specialist_key', 'Specialist'))}"
        with st.expander(title, expanded=True):
            if s.get("parse_error"):
                st.warning("This specialist's output could not be parsed as structured data. Showing raw text.")
                st.code(s.get("raw_text", ""))
                continue
            st.markdown(f"**Confidence:** {s.get('confidence', 'not stated')}")
            st.markdown("**Possible root causes:**")
            for c_ in s.get("possible_root_causes", []):
                st.markdown(f"- {c_}")
            if s.get("cause_basis"):
                st.markdown("**Evidence vs. inference:**")
                for cb in s.get("cause_basis", []):
                    st.markdown(f"- {cb}")
            st.markdown("**Proposed solutions:**")
            for sol in s.get("proposed_solutions", []):
                st.markdown(f"- {sol}")
            st.markdown("**Risks of proposed solutions:**")
            for r in s.get("risks_of_proposed_solutions", []):
                st.markdown(f"- {r}")

    cr = inv.get("critical_review", {})
    st.markdown("<div class='industria-card'>", unsafe_allow_html=True)
    st.markdown("#### \u26A0\uFE0F Critical Reviewer's Assessment")
    if cr.get("parse_error"):
        st.warning("The Critical Reviewer's output could not be parsed as structured data. Showing raw text.")
        st.code(cr.get("raw_text", ""))
    else:
        st.markdown("**Critical findings:**")
        for f in cr.get("critical_findings", []):
            st.markdown(f"- {f}")
        st.markdown("**Alternative explanations:**")
        for a in cr.get("alternative_explanations", []):
            st.markdown(f"- {a}")
        st.markdown("**Unresolved uncertainty:**")
        for u in cr.get("unresolved_uncertainty", []):
            st.markdown(f"- {u}")
        if cr.get("overall_confidence_assessment"):
            st.markdown(f"**Overall confidence assessment:** {cr['overall_confidence_assessment']}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Human Verification")
    col1, col2, col3 = st.columns(3)
    accept_clicked = col1.button("\U0001F7E2 ACCEPT", type="primary", use_container_width=True)
    reject_clicked = col3.button("\U0001F534 REJECT", use_container_width=True)

    with col2:
        if st.session_state.revision_used:
            st.button("\U0001F7E1 MODIFY (used)", disabled=True, use_container_width=True)
            st.caption("One revision has already been used for this problem.")
        else:
            with st.popover("\U0001F7E1 MODIFY / REQUEST REVISION", use_container_width=True):
                feedback = st.text_area(
                    "What should the agents reconsider?",
                    placeholder='e.g. "Consider whether temperature variation could be responsible."',
                )
                resubmit = st.button("Resubmit with this feedback", type="primary")
                if resubmit:
                    if not feedback or not feedback.strip():
                        st.warning("Please enter feedback before resubmitting.")
                    else:
                        st.session_state.human_feedback_history.append(
                            {
                                "timestamp": __import__("datetime").datetime.now().strftime("%H:%M:%S"),
                                "decision": "Modify / Request Revision",
                                "detail": feedback,
                            }
                        )
                        log_audit("Human requested revision", f"— \"{feedback[:80]}\"")
                        confirmed_context_text = build_problem_context_text(confirmed)
                        selected = confirmed.get("selected_specialists", [])
                        with st.spinner("Agents are reconsidering the analysis with your feedback..."):
                            try:
                                investigation = run_with_retry(
                                    run_investigation_crew,
                                    confirmed_context_text=confirmed_context_text,
                                    selected_specialist_keys=selected,
                                    llm_heavy=llm_heavy,
                                    llm_light=llm_light,
                                    feedback=feedback,
                                )
                                st.session_state.investigation_result = investigation
                                st.session_state.revision_used = True
                                log_audit("Revised investigation complete")
                                st.rerun()
                            except Exception as exc:  # noqa: BLE001
                                st.error("Something went wrong during the revision. Please try Accept or Reject.")
                                with st.expander("Technical details"):
                                    st.code(str(exc))

    if accept_clicked:
        log_audit("Human accepted proposed solution")
        report = build_final_report(
            original_problem_statement=st.session_state.problem_statement,
            confirmed=confirmed,
            investigation=inv,
            human_decision="ACCEPTED",
            human_feedback_history=st.session_state.human_feedback_history,
        )
        st.session_state.final_report = report
        st.session_state.stage = "final"
        st.rerun()

    if reject_clicked:
        log_audit("Human rejected proposed solution")
        st.session_state.stage = "stopped"
        st.rerun()

    render_audit_trail()

# ---------------------------------------------------------------------------
# STAGE: final — Verified Decision-Support Report
# ---------------------------------------------------------------------------
elif st.session_state.stage == "final":
    st.markdown("### \u2705 Verified Decision-Support Report")
    report = st.session_state.final_report
    md = report_to_markdown(report)
    st.markdown("<div class='industria-card'>", unsafe_allow_html=True)
    st.markdown(md)
    st.markdown("</div>", unsafe_allow_html=True)

    st.download_button(
        "\U0001F4E5 Download Report (Markdown)",
        data=md,
        file_name="industria_ai_decision_support_report.md",
        mime="text/markdown",
        use_container_width=True,
    )

    if st.button("\U0001F504 Start New Problem", use_container_width=True):
        reset_state()
        st.rerun()

    render_audit_trail()

# ---------------------------------------------------------------------------
# STAGE: stopped
# ---------------------------------------------------------------------------
elif st.session_state.stage == "stopped":
    st.markdown("### \u26D4 Analysis Stopped")
    st.info(
        "The analysis was stopped by human review and no final report was generated. "
        "This is expected behavior when the AI's understanding or proposed solution "
        "was not acceptable — Industria-AI never treats a rejection as an acceptance."
    )
    if st.button("\U0001F504 Start New Problem", use_container_width=True, type="primary"):
        reset_state()
        st.rerun()

    render_audit_trail()
