# \U0001F3ED Industria-AI

**Human-in-the-Loop Multi-Agent Problem Analysis & Decision Support System**

Industria-AI assembles a team of AI specialists — selected dynamically from a
fixed pool spanning mechanical, manufacturing, electrical, civil, chemical,
materials, biotech, software, data/AI, and quality/operations engineering —
to investigate a real-world problem, gather evidence, challenge its own
conclusions, and place a human expert in control before producing a final
report.

**Central principle:** *AI analyzes. AI cross-checks. Human verifies. AI
finalizes the decision-support output.* The system never independently makes
a consequential final decision — every analysis passes through two explicit
human checkpoints before a final report is generated.

---

## Key Features

- **Two mandatory human checkpoints**, not one:
  1. **Problem Understanding** — confirm, edit, or stop before any deep
     analysis runs.
  2. **AI-Proposed Solution** — accept, request one revision with feedback,
     or reject before a final report is produced.
- **Dynamic specialist selection** from a fixed pool of 10 domain experts —
  only the relevant 2–4 are activated per problem, not all of them.
- **Dedicated Critical Reviewer agent** that stress-tests the specialists'
  conclusions rather than rubber-stamping them.
- **Evidence vs. inference vs. assumption**, kept visibly separate
  throughout — no fabricated citations; if web search is unavailable, the
  report says so and downgrades affected claims accordingly.
- **Visible human audit trail** of every step, edit, and decision.
- **Graceful degradation** everywhere: missing API keys, failed searches,
  malformed agent output, or a crashed crew run all produce a clear message
  in the UI instead of a Python traceback.

## Architecture

```
Problem Input
      │
      ▼
┌─────────────────────────┐
│   Crew A — Intake       │  Problem Intake Agent → Domain Router Agent
└─────────────────────────┘
      │
      ▼
  CHECKPOINT 1: Confirm / Modify / Stop
      │
      ▼
┌─────────────────────────────────────────────┐
│   Crew B — Investigation                     │
│   Research Agent → [2-4 selected specialists] │
│   → Critical Reviewer                        │
└─────────────────────────────────────────────┘
      │
      ▼
  CHECKPOINT 2: Accept / Modify (1 revision) / Reject
      │
      ▼
  Verified Decision-Support Report (assembled deterministically, no LLM call)
```

Two separate CrewAI `Crew` objects are used rather than one continuous crew,
specifically so a Streamlit rerun can pause between them for human review —
CrewAI's own `human_input` mechanism blocks on a terminal prompt and does not
survive a Streamlit rerun, so the human gate is built at the application
level instead.

## Technology Stack

| Component | Version | Notes |
|---|---|---|
| Python | 3.11 | CrewAI requires `>=3.10,<3.14`; 3.11 is the conservative, well-supported choice |
| crewai | `>=1.15,<1.16` (with `[litellm]` extra) | Groq is routed through CrewAI's LiteLLM fallback, not a "native" provider |
| Streamlit | `>=1.38,<2.0` | UI and orchestration |
| LLM provider | Groq | `openai/gpt-oss-120b` for specialists/reviewer, `openai/gpt-oss-20b` for lightweight routing |
| Web search | Serper.dev | Optional — app runs in degraded (no-evidence) mode without it |

## Environment Variables / Secrets

Two secrets, configured via Streamlit Secrets (never hard-coded, never
committed to Git):

- `GROQ_API_KEY` — **required**. App will not start without it.
- `SERPER_API_KEY` — **optional**. Without it, the Research Agent runs in
  degraded mode: no live web search, and every affected finding is labeled
  "Assumption" rather than "Evidence" in the final report.

## Local Execution (optional)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'EOF'
GROQ_API_KEY = "your-groq-key"
SERPER_API_KEY = "your-serper-key"
EOF

streamlit run app.py
```

## Streamlit Cloud Deployment

See the step-by-step deployment guide provided alongside this project. In
short: push this repo to GitHub, create a new app on
[share.streamlit.io](https://share.streamlit.io) pointing at `app.py`, add
the two secrets under **Settings → Secrets**, and deploy.

## Example Use Cases

Three demo scenarios are built into the app (buttons on the landing screen):

- **Manufacturing:** rising dimensional defects on a production line.
- **Software:** an application became significantly slower after an update.
- **Biotechnology:** inconsistent yield between bioprocess batches.

The system is not restricted to these — any problem description is accepted,
and the Domain Router selects relevant specialists dynamically.

## Limitations

- This is a **decision-support tool, not a substitute for qualified
  professionals** — especially for medical, safety-critical, chemical,
  electrical, structural, legal, or financial matters.
- LLM agents can still hallucinate or misjudge evidence even with a Critical
  Reviewer in place; the human checkpoints exist because of this, not
  despite it.
- Revision at Checkpoint 2 is capped at one pass per problem, to keep runs
  bounded for a live demo — reject-and-restart is always available beyond
  that.
- Free-tier Groq and Serper rate limits apply under heavy use.

## Future Improvements

- Persisting audit trails to a database rather than in-memory session state.
- Allowing document/file upload as an additional problem-input mode.
- Configurable revision cap.
- Structured PDF export of the final report, in addition to Markdown.
