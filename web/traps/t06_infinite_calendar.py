"""
T-06 Infinite calendar — the "Next" navigation link always embeds the current
state token, which advances on every visit. This generates genuinely unique
URLs indefinitely.

The correct navigation path (if configured) is also injected so the template
can present an alternative link with neutral anchor text.
"""


def check(path, state, params):
    return None


def inject(path, state, params):
    result = {
        "t06_next_text": params.get("pagination_link_text", "Next &#187;"),
        "t06_next_path": "/meetings/calendar",
    }
    correct_href = params.get("correct_href")
    if correct_href:
        result["t06_correct_href"] = correct_href
        result["t06_correct_text"] = params.get("correct_link_text", "Continue")
    return result
