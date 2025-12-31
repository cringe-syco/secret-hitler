from dataclasses import dataclass, field
from typing import Dict, Optional, List

@dataclass
class Player:
    id: str
    name: str
    # nickname: str
    role: Optional[str] = None
    alive: bool = True
    ready: bool = False

@dataclass
class GameState:
    players: Dict[str, Player] = field(default_factory=dict)
    phase: str = "LOBBY"
    president: Optional[str] = None
    chancellor: Optional[str] = None
    liberal_policies: int = 0
    fascist_policies: int = 0
    failed_votes: int = 0
    host_id: Optional[str] = None   # NEW
    votes: Dict[str, str] = field(default_factory=dict)  # player_id -> "JA"/"NEIN"
    last_president: Optional[str] = None
    last_chancellor: Optional[str] = None
    policy_deck: Optional[object] = None
    president_hand: List[str] = field(default_factory=list)
    chancellor_hand: List[str] = field(default_factory=list)
    executive_action: Optional[str] = None
    pending_execution: Optional[str] = None
    party: Optional[str] = None  # "LIBERAL" or "FASCIST"
    veto_requested: bool = False
    veto_approved: bool = False
    investigated_players: set = field(default_factory=set)
    special_president: Optional[str] = None

@dataclass
class GameState(GameState):
    players: Dict[str, Player] = field(default_factory=dict)
    phase: str = "LOBBY"

    host_id: Optional[str] = None

    president_order: List[str] = field(default_factory=list)
    president_index: int = 0
    president: Optional[str] = None
    chancellor: Optional[str] = None

    liberal_policies: int = 0
    fascist_policies: int = 0
    failed_votes: int = 0
