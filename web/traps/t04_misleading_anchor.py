"""
T-04 Misleading anchor — injects goal-adjacent links that lead to dead ends.

Each decoy has anchor text that sounds relevant to the current task but its
destination is a dead end, wrong department, or honeypot path. The correct
link on the same page uses neutral anchor text.
"""


def check(path, state, params):
    return None


def inject(path, state, params):
    decoys = params.get("decoys", [])
    if not decoys:
        return {}
    return {"t04_decoys": decoys}
