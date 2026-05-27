"""
T-05 Honeypot page — injects a prominently-placed link to a structurally
identical page that carries a wrong flag value.

The honeypot URL is registered with the proxy. Visiting it triggers a
honeypot_visit bang and taints the run.

This module only injects the link on the parent page. The honeypot page
itself is a regular template under pages/ with the wrong value baked in.
"""


def check(path, state, params):
    return None


def inject(path, state, params):
    href = params.get("honeypot_path", "")
    text = params.get("link_text", "")
    if not href:
        return {}
    return {"t05_href": href, "t05_text": text}
