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

import litellm

_UNSUPPORTED_KWARGS = ["is_litellm"]
_UNSUPPORTED_MESSAGE_KEYS = ["cache_breakpoint", "cache_control"]
_already_patched = False


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
        return original_completion(*args, **kwargs)

    litellm.completion = patched_completion
    _already_patched = True
