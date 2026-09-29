"""
Custom tools for Industria-AI.

Both tools are defensive by design: neither one ever raises an exception back
into the agent's turn (a raising tool breaks the agent's reasoning loop).
Every failure path returns a plain string the agent can treat as "unavailable".

Each tool also records every call into a per-run usage log (a plain list passed
in by the crew builder) so the UI and final report can show exactly which
tools each agent used. The log is per run, so concurrent users never mix.
"""

import ast
import operator
from datetime import datetime
from typing import Any, Type

import requests
import streamlit as st
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SearchInput(BaseModel):
    query: str = Field(..., description="Short, specific search query, e.g. 'injection molding warpage causes'")


def _record(log, agent, tool, tool_input, status, detail):
    if log is None:
        return
    log.append(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "agent": agent,
            "tool": tool,
            "input": str(tool_input)[:200],
            "status": status,
            "detail": str(detail)[:200],
        }
    )


class WebSearchTool(BaseTool):
    """Serper.dev Google Search wrapper. Used only by the Research Agent."""

    # NOT named "web_search": gpt-oss models have a built-in tool with that
    # name (cursor/id args), which collides and breaks tool calls.
    name: str = "evidence_search"
    args_schema: Type[BaseModel] = SearchInput
    description: str = (
        "Search the web for real, current information relevant to a query. "
        "Input should be a short, specific search query string. "
        "Returns up to 5 results with title, link, and snippet, or a plain "
        "message if web search is unavailable right now."
    )
    agent_label: str = "Research & Evidence Agent"
    usage_log: Any = None

    def _search(self, query: str):
        try:
            api_key = st.secrets.get("SERPER_API_KEY")
        except Exception:  # noqa: BLE001 - no secrets file at all
            api_key = None
        if not api_key:
            return (
                "WEB SEARCH UNAVAILABLE: no SERPER_API_KEY is configured. "
                "Treat this topic as having no external evidence - do not "
                "invent sources or citations.",
                "unavailable",
                "No SERPER_API_KEY configured",
            )
        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 5},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            return ("WEB SEARCH UNAVAILABLE: the search request timed out. Treat this topic as unverified.",
                    "error", "Request timed out")
        except requests.exceptions.RequestException as exc:
            return (f"WEB SEARCH UNAVAILABLE: search request failed ({exc}). Treat this topic as unverified.",
                    "error", "Request failed")
        except ValueError:
            return ("WEB SEARCH UNAVAILABLE: search returned an unreadable response. Treat this topic as unverified.",
                    "error", "Unreadable response")

        organic = data.get("organic", [])
        if not organic:
            return (f'WEB SEARCH returned no results for "{query}". Do not invent sources for this query.',
                    "no results", "0 results")

        lines = [f'Search results for "{query}":']
        for i, item in enumerate(organic[:5], start=1):
            lines.append(
                f"{i}. {item.get('title', 'Untitled')}\n   URL: {item.get('link', '')}\n"
                f"   Snippet: {item.get('snippet', '')}"
            )
        return "\n".join(lines), "ok", f"{min(len(organic), 5)} results"

    def _run(self, query: str) -> str:
        text, status, detail = self._search(query)
        _record(self.usage_log, self.agent_label, self.name, query, status, detail)
        return text


_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants are allowed.")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Expression contains a disallowed element.")


class SafeCalculatorTool(BaseTool):
    """Restricted arithmetic evaluator - AST-parsed, never eval()/exec()."""

    name: str = "safe_calculator"
    description: str = (
        "Evaluate a basic arithmetic expression safely, e.g. '(120 - 95) / 95 * 100'. "
        "Supports + - * / ** and parentheses only. Input must be a single "
        "expression string, not a word problem."
    )
    agent_label: str = ""
    usage_log: Any = None

    def _run(self, expression: str) -> str:
        try:
            tree = ast.parse(expression, mode="eval")
            result = str(_safe_eval(tree.body))
            _record(self.usage_log, self.agent_label, self.name, expression, "ok", f"= {result}")
            return result
        except ZeroDivisionError:
            _record(self.usage_log, self.agent_label, self.name, expression, "error", "Division by zero")
            return "Error: division by zero. Report this calculation as unavailable rather than guessing a number."
        except Exception as exc:  # noqa: BLE001 - must never raise
            _record(self.usage_log, self.agent_label, self.name, expression, "error", "Invalid expression")
            return f"Error: could not evaluate expression ({exc}). Report this calculation as unavailable rather than guessing a number."


# ---------------------------------------------------------------------------
# Academic literature search (OpenAlex)
# ---------------------------------------------------------------------------
def _abstract_snippet(inverted_index, max_words=45) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        for i in idxs or []:
            positions.append((i, word))
    positions.sort()
    words = [w for _, w in positions[:max_words]]
    text = " ".join(words)
    return text + (" ..." if len(positions) > max_words else "")


def _openalex_meta(work: dict):
    """Extract clean citation metadata from one OpenAlex work record."""
    if not isinstance(work, dict):
        return None
    wid = str(work.get("id") or "").rsplit("/", 1)[-1]
    title = work.get("display_name") or work.get("title")
    if not wid.startswith("W") or not title:
        return None
    authors = []
    for a in work.get("authorships") or []:
        name = ((a or {}).get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    source = ((work.get("primary_location") or {}).get("source") or {})
    doi = work.get("doi") or ""
    return {
        "id": wid,
        "title": str(title),
        "authors": authors,
        "year": work.get("publication_year") or "n.d.",
        "venue": source.get("display_name") or "",
        "doi": doi,
        "url": doi if doi else f"https://openalex.org/{wid}",
        "cited_by": work.get("cited_by_count") or 0,
        "abstract": _abstract_snippet(work.get("abstract_inverted_index")),
    }


class ScholarlySearchTool(BaseTool):
    """
    Searches peer-reviewed literature via the OpenAlex API. Every paper it
    returns is stored in a per-run registry keyed by its OpenAlex ID, so the
    final reference list is built from real metadata - never from text the
    model wrote. Any ID the model cites that is not in the registry is dropped.
    """

    name: str = "scholarly_search"
    args_schema: Type[BaseModel] = SearchInput
    description: str = (
        "Search peer-reviewed academic and research literature. Input: a short, "
        "specific query string. Returns up to 5 papers, each labelled with a "
        "reference ID in square brackets like [W2741809807]. Cite academic "
        "papers ONLY with these exact IDs; never invent one."
    )
    agent_label: str = "Research & Evidence Agent"
    usage_log: Any = None
    registry: Any = None

    def _run(self, query: str) -> str:
        try:
            api_key = st.secrets.get("OPENALEX_API_KEY")
        except Exception:  # noqa: BLE001
            api_key = None
        if not api_key:
            _record(self.usage_log, self.agent_label, self.name, query, "unavailable", "No OPENALEX_API_KEY configured")
            return ("ACADEMIC SEARCH UNAVAILABLE: no OPENALEX_API_KEY is configured. "
                    "Do not cite any academic papers or invent reference IDs.")
        try:
            response = requests.get(
                "https://api.openalex.org/works",
                params={"search": query, "per_page": 5, "api_key": api_key},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            _record(self.usage_log, self.agent_label, self.name, query, "error", "Request timed out")
            return "ACADEMIC SEARCH UNAVAILABLE: request timed out. Do not invent academic citations."
        except requests.exceptions.RequestException:
            _record(self.usage_log, self.agent_label, self.name, query, "error", "Request failed")
            return "ACADEMIC SEARCH UNAVAILABLE: request failed. Do not invent academic citations."
        except ValueError:
            _record(self.usage_log, self.agent_label, self.name, query, "error", "Unreadable response")
            return "ACADEMIC SEARCH UNAVAILABLE: unreadable response. Do not invent academic citations."

        papers = [m for m in (_openalex_meta(w) for w in (data.get("results") or [])) if m]
        if not papers:
            _record(self.usage_log, self.agent_label, self.name, query, "no results", "0 papers")
            return f'ACADEMIC SEARCH returned no papers for "{query}". Do not invent academic citations.'

        lines = [f'Academic papers for "{query}":']
        for p in papers:
            if isinstance(self.registry, dict):
                self.registry[p["id"]] = p
            authors = ", ".join(p["authors"][:3]) + (" et al." if len(p["authors"]) > 3 else "")
            lines.append(
                f"[{p['id']}] {p['title']} ({p['year']}). {(authors or 'Unknown authors').rstrip('.')}. "
                f"{p['venue'] or 'Unknown venue'}. Cited by {p['cited_by']}.\n"
                f"   Abstract: {p['abstract'] or '(not available)'}"
            )
        _record(self.usage_log, self.agent_label, self.name, query, "ok", f"{len(papers)} papers")
        return "\n".join(lines)
