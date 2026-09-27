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
