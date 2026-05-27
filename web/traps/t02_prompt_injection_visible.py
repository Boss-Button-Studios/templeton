"""
T-02 Visible prompt injection — injects a styled "official notice" block into
the page body containing false instructions.

The notice is rendered in normal body text at a plausible visual weight so that
an agent that follows embedded instructions will extract the wrong value.
"""


def check(path, state, params):
    return None


def inject(path, state, params):
    text = params.get("injection_text", "")
    if not text:
        return {}
    return {"t02_injection": text}
