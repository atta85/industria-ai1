from datetime import datetime

import streamlit as st

DEFAULTS = {
    "stage": "input",
    "problem_statement": "",
    "industry": "",
    "objective": "",
    "constraints_input": "",
    "available_data": "",
    "desired_outcome": "",
    "intake_result": None,
    "confirmed": None,
    "investigation_result": None,
    "revision_used": False,
    "human_feedback_history": [],
    "audit_trail": [],
    "final_report": None,
    "prefill_problem": "",
}


def init_state():
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_state():
    for key, value in DEFAULTS.items():
        st.session_state[key] = value


def log_audit(event: str, detail: str = ""):
    st.session_state.audit_trail.append(
        {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "event": event,
            "detail": detail,
        }
    )
