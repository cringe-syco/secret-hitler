import random

def assign_roles(player_ids):
    n = len(player_ids)
    roles = ["HITLER"]
    fascists = 1 if n <= 6 else 2 if n <= 8 else 3
    roles += ["FASCIST"] * fascists
    roles += ["LIBERAL"] * (n - len(roles))
    random.shuffle(roles)
    return dict(zip(player_ids, roles))
