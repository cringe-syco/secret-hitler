from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import uuid
import random
from typing import Dict

from game.state import GameState, Player
from game.roles import assign_roles
from game.deck import PolicyDeck


# ============================================================
# App & Global State
# ============================================================

app = FastAPI()
app.mount("/static", StaticFiles(directory="web", html=True))

game = GameState()
clients: Dict[str, WebSocket] = {}


# ============================================================
# HTTP
# ============================================================

@app.get("/")
async def index():
    return FileResponse("web/index.html")


# ============================================================
# WebSocket Entrypoint
# ============================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    player_id = register_player(ws)
    await broadcast_state()

    try:
        while True:
            msg = await ws.receive_json()
            await handle_action(player_id, msg)

    except Exception as e:
        print(f"[WS ERROR] {e}")
        unregister_player(player_id)
        await broadcast_state()


# ============================================================
# Player Lifecycle
# ============================================================

def register_player(ws: WebSocket) -> str:
    player_id = str(uuid.uuid4())[:8]
    clients[player_id] = ws

    game.players[player_id] = Player(
        id=player_id,
        name=f"Player-{len(game.players) + 1}"
    )

    if game.host_id is None:
        game.host_id = player_id

    return player_id


def unregister_player(player_id: str):
    clients.pop(player_id, None)
    game.players.pop(player_id, None)

    if game.host_id == player_id:
        game.host_id = next(iter(game.players), None)


# ============================================================
# Action Dispatcher
# ============================================================

async def handle_action(player_id: str, msg: dict):
    action = msg.get("action")

    if action == "SET_READY":
        await handle_ready(player_id, msg)

    elif action == "START_GAME":
        await handle_start_game(player_id)

    elif action == "NOMINATE":
        await handle_nomination(player_id, msg)

    elif action == "VOTE":
        await handle_vote(player_id, msg)

    elif action == "PRESIDENT_DISCARD":
        await handle_president_discard(player_id, msg)

    elif action == "CHANCELLOR_DISCARD":
        await handle_chancellor_discard(player_id, msg)
    
    elif action == "EXECUTE_PLAYER":
        await handle_execution(player_id, msg)
    
    elif action == "REQUEST_VETO":
        await handle_veto_request(player_id)

    elif action == "APPROVE_VETO":
        await handle_veto_decision(player_id, approve=True)

    elif action == "REJECT_VETO":
        await handle_veto_decision(player_id, approve=False)

    elif action == "INVESTIGATE_PLAYER":
        await handle_investigation(player_id, msg)

    elif action == "SPECIAL_ELECTION":
        await handle_special_election(player_id, msg)

    elif action == "POLICY_PEEK":
        await handle_policy_peek(player_id)



# ============================================================
# Lobby & Voting
# ============================================================

async def handle_ready(player_id: str, msg: dict):
    if game.phase != "LOBBY":
        return

    game.players[player_id].ready = bool(msg.get("value"))
    await broadcast_state()


async def handle_start_game(player_id: str):
    if player_id != game.host_id:
        return

    if game.phase != "LOBBY":
        return

    if len(game.players) < 5:
        return

    if any(
        pid != game.host_id and not p.ready
        for pid, p in game.players.items()
    ):
        return

    start_game()
    await broadcast_state()


async def handle_nomination(player_id: str, msg: dict):
    if game.phase != "NOMINATION":
        return

    if player_id != game.president:
        return

    nominee = msg.get("value")

    if not is_eligible_chancellor(nominee):
        return

    game.chancellor = nominee
    game.phase = "VOTING"
    game.votes = {}
    await broadcast_state()


async def handle_vote(player_id: str, msg: dict):
    if game.phase != "VOTING":
        return

    if not game.players[player_id].alive:
        return

    vote = msg.get("value")
    if vote not in ("JA", "NEIN"):
        return

    game.votes[player_id] = vote

    alive_players = [
        pid for pid, p in game.players.items() if p.alive
    ]

    if len(game.votes) == len(alive_players):
        await resolve_votes()

async def handle_execution(player_id: str, msg: dict):
    if game.phase != "EXECUTIVE":
        return

    if game.executive_action != "EXECUTE":
        return

    if player_id != game.president:
        return

    target = msg.get("value")

    if target not in game.players:
        return

    if not game.players[target].alive:
        return

    game.players[target].alive = False

    # HITLER EXECUTED → LIBERALS WIN
    if is_hitler(target):
        game.phase = "GAME_OVER"
        game.winner = "LIBERALS"
        await broadcast_state()
        return

    game.executive_action = None
    rotate_president()
    game.phase = "NOMINATION"

    await broadcast_state()

async def handle_special_election(player_id: str, msg: dict):
    if game.phase != "EXECUTIVE":
        return
    if game.executive_action != "SPECIAL_ELECTION":
        return
    if player_id != game.president:
        return

    target = msg.get("value")
    if target not in game.players or not game.players[target].alive:
        return

    # Save normal rotation
    game.saved_president_index = game.president_index
    game.president = target
    game.chancellor = None

    game.executive_action = None
    game.phase = "NOMINATION"

    await broadcast_state()


async def handle_policy_peek(player_id: str):
    if game.phase != "EXECUTIVE":
        return
    if game.executive_action != "POLICY_PEEK":
        return
    if player_id != game.president:
        return

    peek = game.policy_deck.deck[:3]

    await clients[player_id].send_json({
        "type": "POLICY_PEEK",
        "cards": peek
    })

    game.executive_action = None
    rotate_president()
    game.phase = "NOMINATION"

    await broadcast_state()


async def handle_veto_request(player_id: str):
    if game.phase != "LEGISLATIVE":
        return
    if player_id != game.chancellor:
        return
    if game.fascist_policies < 5:
        return

    game.veto_requested = True
    await broadcast_state()

async def handle_veto_decision(player_id: str, approve: bool):
    if game.phase != "LEGISLATIVE":
        return
    if player_id != game.president:
        return
    if not game.veto_requested:
        return

    game.veto_requested = False

    if approve:
        game.failed_votes += 1

        if game.failed_votes == 3:
            chaos_policy = game.policy_deck.draw(1)[0]
            enact_policy(chaos_policy)
            game.failed_votes = 0

        rotate_president()
        game.phase = "NOMINATION"

    else:
        # Chancellor must enact normally
        game.phase = "LEGISLATIVE"

    await broadcast_state()

async def handle_investigation(player_id: str, msg: dict):
    if game.phase != "EXECUTIVE":
        return
    if game.executive_action != "INVESTIGATE":
        return
    if player_id != game.president:
        return

    target = msg.get("value")
    if (
        target not in game.players
        or not game.players[target].alive
        or target in game.investigated_players
    ):
        return

    game.investigated_players.add(target)

    await clients[player_id].send_json({
        "type": "INVESTIGATION_RESULT",
        "player": game.players[target].name,
        "party": game.players[target].party
    })

    game.executive_action = None
    rotate_president()
    game.phase = "NOMINATION"

    await broadcast_state()


# ============================================================
# Game Flow
# ============================================================

def start_game():
    game.policy_deck = PolicyDeck()
    game.failed_votes = 0
    game.investigated_players = set()

    roles = assign_roles(list(game.players.keys()))
    for pid, role in roles.items():
        game.players[pid].role = role
        game.players[pid].ready = False

    for pid, player in game.players.items():
        if player.role == "LIBERAL":
            player.party = "LIBERAL"
        else:
            player.party = "FASCIST"  # Hitler is Fascist party

    game.president_order = list(game.players.keys())
    random.shuffle(game.president_order)

    game.president_index = 0
    game.president = game.president_order[0]
    game.chancellor = None

    game.last_president = None
    game.last_chancellor = None
    game.phase = "NOMINATION"


async def resolve_votes():
    ja = sum(v == "JA" for v in game.votes.values())
    nein = sum(v == "NEIN" for v in game.votes.values())
    passed = ja > nein

    await broadcast_vote_result(ja, nein, passed)

    if passed:
        game.failed_votes = 0

        # HITLER ELECTED CHANCELLOR INSTANT WIN
        if (
            game.fascist_policies >= 3
            and is_hitler(game.chancellor)
        ):
            game.phase = "GAME_OVER"
            game.winner = "FASCISTS"
            await broadcast_state()
            return

        game.phase = "LEGISLATIVE"
        game.president_hand = game.policy_deck.draw(3)
        game.chancellor_hand = []


    else:
        game.failed_votes += 1

        if game.failed_votes == 3:
            chaos_policy = game.policy_deck.draw(1)[0]
            enact_policy(chaos_policy)
            game.failed_votes = 0
            rotate_president()
            game.phase = "NOMINATION"
        else:
            rotate_president()
            game.phase = "NOMINATION"

    game.votes = {}
    await broadcast_state()


# ============================================================
# Legislative Phase
# ============================================================

async def handle_president_discard(player_id: str, msg: dict):
    if game.phase != "LEGISLATIVE":
        return
    if player_id != game.president:
        return

    card = msg.get("value")
    if card not in game.president_hand:
        return

    game.president_hand.remove(card)
    game.policy_deck.discard_card(card)

    game.chancellor_hand = game.president_hand.copy()
    game.president_hand = []

    await broadcast_state()


async def handle_chancellor_discard(player_id: str, msg: dict):
    if game.phase != "LEGISLATIVE":
        return
    if player_id != game.chancellor:
        return

    card = msg.get("value")
    if card not in game.chancellor_hand:
        return

    game.chancellor_hand.remove(card)
    game.policy_deck.discard_card(card)

    enacted = game.chancellor_hand.pop()
    enact_policy(enacted)

    game.chancellor_hand = []
    rotate_president()
    game.phase = "NOMINATION"

    await broadcast_state()


def enact_policy(card: str):
    if card == "L":
        game.liberal_policies += 1
        check_win_conditions()
        return

    game.fascist_policies += 1

    check_win_conditions()

    power = get_executive_power()
    if power and game.phase != "GAME_OVER":
        game.executive_action = power
        game.phase = "EXECUTIVE"

    check_win_conditions()


def check_win_conditions():
    if game.liberal_policies >= 5:
        game.phase = "GAME_OVER"
    if game.fascist_policies >= 6:
        game.phase = "GAME_OVER"

def is_hitler(player_id: str) -> bool:
    return game.players[player_id].role == "HITLER"

def get_executive_power():
    fp = game.fascist_policies
    players = len(game.players)

    if players <= 6:
        if fp == 3:
            return "POLICY_PEEK"
        if fp == 4:
            return "EXECUTE"
        if fp == 5:
            return "EXECUTE"

    else:
        if fp == 2:
            return "INVESTIGATE"
        if fp == 3:
            return "SPECIAL_ELECTION"
        if fp == 4:
            return "EXECUTE"
        if fp == 5:
            return "EXECUTE"

    return None

# ============================================================
# Rotation & Eligibility
# ============================================================

def rotate_president():
    game.last_president = game.president
    game.last_chancellor = game.chancellor

    if game.saved_president_index is not None:
        game.president_index = game.saved_president_index
        game.saved_president_index = None
    else:
        game.president_index = (
            game.president_index + 1
        ) % len(game.president_order)

    game.president = game.president_order[game.president_index]
    game.chancellor = None



def is_eligible_chancellor(nominee: str) -> bool:
    if nominee not in game.players:
        return False

    if not game.players[nominee].alive:
        return False

    if nominee == game.president:
        return False

    if len(game.players) > 5:
        if nominee == game.last_chancellor:
            return False
        if nominee == game.last_president:
            return False

    return True


# ============================================================
# Broadcasting
# ============================================================

async def broadcast_vote_result(ja: int, nein: int, passed: bool):
    for ws in clients.values():
        await ws.send_json({
            "type": "VOTE_RESULT",
            "ja": ja,
            "nein": nein,
            "passed": passed
        })


async def broadcast_state():
    for pid, ws in clients.items():
        await ws.send_json({
            "type": "STATE",
            "phase": game.phase,
            "host_id": game.host_id,
            "you": {
                "id": pid,
                "role": game.players[pid].role,
                "ready": game.players[pid].ready,
                "is_host": pid == game.host_id,
                "president_hand": game.president_hand if pid == game.president else [],
                "chancellor_hand": game.chancellor_hand if pid == game.chancellor else []
            },
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "alive": p.alive,
                    "ready": p.ready,
                    "is_host": p.id == game.host_id
                }
                for p in game.players.values()
            ],
            "public": {
                "president": game.president,
                "chancellor": game.chancellor,
                "failed_votes": game.failed_votes,
                "executive_action": game.executive_action

            }
        })
