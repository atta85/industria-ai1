"""
Groq is routed through CrewAI's LiteLLM fallback path (Groq is not one of
CrewAI's small list of "native" providers - only OpenAI, Anthropic, Azure,
Google, and Bedrock get first-class treatment). Community reports document a
real failure mode on this path: litellm.completion() can receive an internal
`is_litellm` keyword argument that Groq's own client rejects, surfacing as
`GroqException: is_litellm is unsupported`.

This patch strips that one internal key from outgoing kwargs before they
reach litellm.completion(). It is a no-op (and harmless) if the key is never
present, so it is safe to apply unconditionally at app startup rather than
waiting for the error to occur.
"""

import re
import time

import litellm

_UNSUPPORTED_KWARGS = ["is_litellm"]
_UNSUPPORTED_MESSAGE_KEYS = ["cache_breakpoint", "cache_control"]
_MAX_RATE_LIMIT_RETRIES = 6
_already_patched = False

_WAIT_PATTERN = re.compile(r"try again in ([\d.]+)(ms|s)", re.IGNORECASE)


def _extract_wait_seconds(exc: Exception, fallback: float) -> float:
    match = _WAIT_PATTERN.search(str(exc))
    if not match:
        return fallback
    value, unit = match.groups()
    value = float(value)
    return value / 1000.0 if unit.lower() == "ms" else value


def apply_groq_litellm_patch():
    global _already_patched
    if _already_patched:
        return

    original_completion = litellm.completion

    def patched_completion(*args, **kwargs):
        for key in _UNSUPPORTED_KWARGS:
            kwargs.pop(key, None)
        for msg in kwargs.get("messages", []):
            if isinstance(msg, dict):
                for key in _UNSUPPORTED_MESSAGE_KEYS:
                    msg.pop(key, None)

        # Retry only THIS single API call on a rate limit - not the whole
        # crew - so we don't re-spend tokens on agents that already
        # succeeded. Groq's error message tells us the exact wait needed.
        for attempt in range(_MAX_RATE_LIMIT_RETRIES):
            try:
                return original_completion(*args, **kwargs)
            except litellm.RateLimitError as exc:
                if attempt == _MAX_RATE_LIMIT_RETRIES - 1:
                    raise
                wait_s = _extract_wait_seconds(exc, fallback=2.0 * (attempt + 1))
                time.sleep(wait_s + 0.5)  # small buffer past the reported wait

    litellm.completion = patched_completion
    _already_patched = True
