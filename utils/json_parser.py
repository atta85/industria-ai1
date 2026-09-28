"""
Agents are instructed to return raw JSON, but LLMs sometimes wrap it in
markdown code fences, add a stray sentence before/after it, or occasionally
produce malformed JSON entirely. This helper degrades gracefully in every
case instead of raising - a parse failure becomes visible data in the UI
(with a warning) rather than a crashed app.
"""

import json
import re


def _dict_or_fallback(obj, raw_text):
    if isinstance(obj, dict):
        return obj
    return {"raw_text": raw_text if raw_text is not None else "", "parse_error": True}


def as_str_list(value) -> list:
    """Coerce LLM output into a clean list of strings (handles str, dict items, None)."""
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        value = [value]
    if isinstance(value, dict):
        value = [value]
    out = []
    for item in value:
        if isinstance(item, dict):
            item = "; ".join(f"{k}: {v}" for k, v in item.items())
        item = str(item).strip()
        if item:
            out.append(item)
    return out


def as_evidence_list(value) -> list:
    """Coerce evidence into a list of {finding, source_title, source_url} dicts."""
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        value = [value]
    out = []
    for item in value:
        if isinstance(item, dict):
            out.append({
                "finding": str(item.get("finding", item.get("summary", ""))),
                "source_title": str(item.get("source_title", item.get("title", ""))),
                "source_url": str(item.get("source_url", item.get("url", ""))),
            })
        elif str(item).strip():
            out.append({"finding": str(item).strip(), "source_title": "", "source_url": ""})
    return out


def parse_json_output(raw_text: str) -> dict:
    if raw_text is None:
        return {"raw_text": "", "parse_error": True}

    text = raw_text.strip()

    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return _dict_or_fallback(json.loads(text), raw_text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Last resort: grab the widest {...} span and try again.
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return _dict_or_fallback(json.loads(brace_match.group(0)), raw_text)
        except json.JSONDecodeError:
            pass

    return {"raw_text": raw_text, "parse_error": True}
