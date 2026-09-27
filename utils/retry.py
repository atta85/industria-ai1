"""
Groq's free tier has a low tokens-per-minute cap, which is easy to hit when
several agents run back-to-back in one investigation. Rather than surfacing
a rate-limit crash to the human mid-analysis, this retries with a short
backoff - the wait Groq reports is usually under a second.
"""

import time

import litellm


def run_with_retry(fn, *args, max_retries=5, base_delay=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except litellm.RateLimitError:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (attempt + 1))
    return fn(*args, **kwargs)
