"""
Agents are instructed to return raw JSON, but LLMs sometimes wrap it in
markdown code fences, add a stray sentence before/after it, or occasionally
produce malformed JSON entirely. This helper degrades gracefully in every
case instead of raising - a parse failure becomes visible data in the UI
(with a warning) rather than a crashed app.
"""

import json
import re


def parse_json_output(raw_text: str) -> dict:
    if raw_text is None:
        return {"raw_text": "", "parse_error": True}

    text = raw_text.strip()

    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Last resort: grab the widest {...} span and try again.
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return {"raw_text": raw_text, "parse_error": True}
