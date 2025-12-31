ALLOWED = {
    "LOBBY": {"START"},
    "NOMINATION": {"NOMINATE"},
    "VOTING": {"VOTE"},
    "LEGISLATIVE": {"DISCARD"},
    "EXECUTIVE": {"EXECUTE"},
}

def validate(phase, action):
    if action not in ALLOWED.get(phase, set()):
        raise ValueError("Invalid action for phase")
