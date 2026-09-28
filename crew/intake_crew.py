import os

import yaml
from crewai import Agent, Crew, Process, Task

from utils.json_parser import as_str_list, parse_json_output

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")


def _load_yaml(filename: str) -> dict:
    with open(os.path.join(_CONFIG_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_intake_crew(
    problem_statement: str,
    industry: str,
    objective: str,
    constraints: str,
    available_data: str,
    desired_outcome: str,
    llm_light,
) -> dict:
    """
    Runs the two-agent Intake Crew (Problem Intake -> Domain Router) and
    returns a single merged dict ready for Checkpoint 1 display:
      problem_summary, objectives, constraints, assumptions,
      missing_information, domains, selected_specialists, routing_rationale
    """
    agents_config = _load_yaml("agents.yaml")
    tasks_config = _load_yaml("tasks.yaml")

    intake_agent = Agent(
        config=agents_config["problem_intake"],
        llm=llm_light,
        verbose=True,
        allow_delegation=False,
    )
    router_agent = Agent(
        config=agents_config["domain_router"],
        llm=llm_light,
        verbose=True,
        allow_delegation=False,
    )

    intake_task = Task(
        description=tasks_config["intake_task"]["description"].format(
            problem_statement=problem_statement or "(not provided)",
            industry=industry or "(not provided)",
            objective=objective or "(not provided)",
            constraints=constraints or "(not provided)",
            available_data=available_data or "(not provided)",
            desired_outcome=desired_outcome or "(not provided)",
        ),
        expected_output=tasks_config["intake_task"]["expected_output"],
        agent=intake_agent,
    )

    routing_task = Task(
        description=tasks_config["routing_task"]["description"],
        expected_output=tasks_config["routing_task"]["expected_output"],
        agent=router_agent,
        context=[intake_task],
    )

    crew = Crew(
        agents=[intake_agent, router_agent],
        tasks=[intake_task, routing_task],
        process=Process.sequential,
        verbose=True,
    )
    crew.kickoff()

    intake_data = parse_json_output(intake_task.output.raw if intake_task.output else None)
    routing_data = parse_json_output(routing_task.output.raw if routing_task.output else None)

    # Validate selected specialists against the fixed pool - if the router
    # hallucinated a key that doesn't exist, drop it rather than crash later.
    from crew.specialist_pool import SPECIALIST_POOL

    raw_selected = as_str_list(routing_data.get("selected_specialists"))
    valid_selected = [k for k in raw_selected if k in SPECIALIST_POOL]

    merged = {
        "problem_summary": str(intake_data.get("problem_summary", "")),
        "objectives": as_str_list(intake_data.get("objectives")),
        "constraints": as_str_list(intake_data.get("constraints")),
        "assumptions": as_str_list(intake_data.get("assumptions")),
        "missing_information": as_str_list(intake_data.get("missing_information")),
        "domains": as_str_list(routing_data.get("domains")),
        "selected_specialists": valid_selected,
        "routing_rationale": str(routing_data.get("routing_rationale", "")),
        "intake_parse_error": intake_data.get("parse_error", False),
        "routing_parse_error": routing_data.get("parse_error", False),
    }
    return merged
