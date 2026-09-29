import os

import yaml
from crewai import Agent, Crew, Process, Task

from crew.specialist_pool import SPECIALIST_POOL
from crew.tools.custom_tools import SafeCalculatorTool, ScholarlySearchTool, WebSearchTool
from utils.citations import apply_citations
from utils.json_parser import as_evidence_list, as_str_list, parse_json_output

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")


def _load_yaml(filename: str) -> dict:
    with open(os.path.join(_CONFIG_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_investigation_crew(
    confirmed_context_text: str,
    selected_specialist_keys: list,
    llm_heavy,
    llm_light,
    feedback: str = None,
) -> dict:
    """
    Runs the Investigation Crew: Research Agent -> selected specialists (in
    parallel conceptually, sequential in execution) -> Critical Reviewer.
    Returns a dict with evidence, per-specialist findings, and the critical
    review, ready for Checkpoint 2 display.

    If `feedback` is provided (the human chose Modify at Checkpoint 2), it is
    injected into every task as a revision note so agents explicitly
    reconsider their analysis in light of it.
    """
    agents_config = _load_yaml("agents.yaml")
    tasks_config = _load_yaml("tasks.yaml")

    revision_note = (
        f'IMPORTANT - the human reviewer requested reconsideration with this '
        f'feedback: "{feedback}". Take this feedback seriously and adjust '
        f"your analysis accordingly rather than repeating your previous conclusions unchanged."
        if feedback
        else ""
    )

    tool_log = []  # per-run record of every tool call, shown in the UI/report
    reference_registry = {}  # papers actually returned by scholarly_search this run

    # --- Research Agent ---
    research_agent = Agent(
        config=agents_config["research_agent"],
        llm=llm_light,
        tools=[WebSearchTool(usage_log=tool_log), ScholarlySearchTool(usage_log=tool_log, registry=reference_registry)],
        verbose=True,
        allow_delegation=False,
    )
    research_task = Task(
        description=tasks_config["research_task"]["description"].format(
            confirmed_problem_context=confirmed_context_text
        ),
        expected_output=tasks_config["research_task"]["expected_output"],
        agent=research_agent,
    )

    # --- Selected specialists (dynamic selection from the fixed pool) ---
    specialist_agents = {}
    specialist_tasks = {}
    template_desc = tasks_config["specialist_task_template"]
    template_output = tasks_config["specialist_task_expected_output"]

    for key in selected_specialist_keys:
        if key not in agents_config:
            continue  # defensive: ignore any key not present in agents.yaml
        role_label = agents_config[key]["role"]
        agent = Agent(
            config=agents_config[key],
            llm=llm_heavy,
            tools=[SafeCalculatorTool(agent_label=role_label, usage_log=tool_log)],
            verbose=True,
            allow_delegation=False,
        )
        task = Task(
            description=template_desc.format(
                specialist_role=role_label,
                confirmed_problem_context=confirmed_context_text,
                revision_note=revision_note,
            ),
            expected_output=template_output.format(specialist_role=role_label),
            agent=agent,
            context=[research_task],
        )
        specialist_agents[key] = agent
        specialist_tasks[key] = task

    # --- Critical Reviewer ---
    critical_reviewer_agent = Agent(
        config=agents_config["critical_reviewer"],
        llm=llm_heavy,
        verbose=True,
        allow_delegation=False,
    )
    critical_review_task = Task(
        description=tasks_config["critical_review_task"]["description"].format(
            confirmed_problem_context=confirmed_context_text,
            revision_note=revision_note,
        ),
        expected_output=tasks_config["critical_review_task"]["expected_output"],
        agent=critical_reviewer_agent,
        context=[research_task] + list(specialist_tasks.values()),
    )

    all_agents = [research_agent] + list(specialist_agents.values()) + [critical_reviewer_agent]
    all_tasks = [research_task] + list(specialist_tasks.values()) + [critical_review_task]

    crew = Crew(agents=all_agents, tasks=all_tasks, process=Process.sequential, verbose=True)
    crew.kickoff()

    evidence_data = parse_json_output(research_task.output.raw if research_task.output else None)

    specialist_results = []
    for key, task in specialist_tasks.items():
        result = parse_json_output(task.output.raw if task.output else None)
        if not result.get("parse_error"):
            for field in ("possible_root_causes", "cause_basis", "proposed_solutions", "risks_of_proposed_solutions"):
                result[field] = as_str_list(result.get(field))
            result["confidence"] = str(result.get("confidence", "not stated"))
            result["specialist"] = str(result.get("specialist", agents_config[key]["role"]))
        result["specialist_key"] = key
        result["specialist_icon"] = SPECIALIST_POOL.get(key, {}).get("icon", "")
        specialist_results.append(result)

    critical_review_data = parse_json_output(
        critical_review_task.output.raw if critical_review_task.output else None
    )

    if not critical_review_data.get("parse_error"):
        for field in ("critical_findings", "alternative_explanations", "unresolved_uncertainty"):
            critical_review_data[field] = as_str_list(critical_review_data.get(field))
        if "overall_confidence_assessment" in critical_review_data:
            critical_review_data["overall_confidence_assessment"] = str(critical_review_data["overall_confidence_assessment"])

    evidence_list = as_evidence_list(evidence_data.get("evidence"))
    agents_involved = [agents_config["research_agent"]["role"]]
    agents_involved += [agents_config[k]["role"] for k in specialist_tasks.keys()]
    agents_involved.append(agents_config["critical_reviewer"]["role"])

    result = {
        "evidence_available": bool(evidence_list),
        "evidence": evidence_list,
        "evidence_notes": str(evidence_data.get("notes", "")),
        "specialist_results": specialist_results,
        "critical_review": critical_review_data,
        "agents_involved": agents_involved,
        "tool_usage": tool_log,
    }
    return apply_citations(result, reference_registry)
