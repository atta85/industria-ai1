"""
Custom tools for Industria-AI.

Both tools are defensive by design: neither one ever raises an exception back
into the agent's turn. A tool that raises breaks the agent's reasoning loop
mid-task, which is exactly the kind of crash the app's error-handling rules
are meant to prevent. Instead, every failure path returns a plain string that
the agent (and, ultimately, the report) can treat as "unavailable" rather
than as a crash.
"""

import ast
import operator

import requests
import streamlit as st
from crewai.tools import BaseTool


class WebSearchTool(BaseTool):
    """
    Wraps Serper.dev's Google Search API directly (rather than depending on a
    third-party wrapper package) so failure handling is fully under our
    control. Used only by the Research Agent.
    """

    name: str = "web_search"
    description: str = (
        "Search the web for real, current information relevant to a query. "
        "Input should be a short, specific search query string. "
        "Returns up to 5 results with title, link, and snippet, or a plain "
        "message if web search is unavailable right now."
    )

    def _run(self, query: str) -> str:
        api_key = st.secrets.get("SERPER_API_KEY")
        if not api_key:
            return (
                "WEB SEARCH UNAVAILABLE: no SERPER_API_KEY is configured. "
                "Treat this topic as having no external evidence - do not "
                "invent sources or citations."
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
            return "WEB SEARCH UNAVAILABLE: the search request timed out. Treat this topic as unverified."
        except requests.exceptions.RequestException as exc:
            return f"WEB SEARCH UNAVAILABLE: search request failed ({exc}). Treat this topic as unverified."
        except ValueError:
            return "WEB SEARCH UNAVAILABLE: search returned an unreadable response. Treat this topic as unverified."

        organic = data.get("organic", [])
        if not organic:
            return f'WEB SEARCH returned no results for "{query}". Do not invent sources for this query.'

        lines = [f'Search results for "{query}":']
        for i, item in enumerate(organic[:5], start=1):
            title = item.get("title", "Untitled")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            lines.append(f"{i}. {title}\n   URL: {link}\n   Snippet: {snippet}")
        return "\n".join(lines)


# Only a safe, whitelisted subset of arithmetic operators is ever evaluated.
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
    """
    A restricted arithmetic evaluator. Deliberately does NOT use eval() or
    exec() - the expression is parsed into an AST and only numeric literals
    plus + - * / ** ( ) are permitted, so a malformed or adversarial
    expression from a model can never execute arbitrary code.
    """

    name: str = "safe_calculator"
    description: str = (
        "Evaluate a basic arithmetic expression safely, e.g. '(120 - 95) / 95 * 100'. "
        "Supports + - * / ** and parentheses only. Input must be a single "
        "expression string, not a word problem."
    )

    def _run(self, expression: str) -> str:
        try:
            tree = ast.parse(expression, mode="eval")
            result = _safe_eval(tree.body)
            return str(result)
        except ZeroDivisionError:
            return "Error: division by zero. Report this calculation as unavailable rather than guessing a number."
        except Exception as exc:  # noqa: BLE001 - intentionally broad, this must never raise
            return f"Error: could not evaluate expression ({exc}). Report this calculation as unavailable rather than guessing a number."
