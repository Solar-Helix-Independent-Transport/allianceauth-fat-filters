from __future__ import division
from datetime import datetime
from ninja import Schema

from typing import Optional, List, Dict


class Character(Schema):
    character_name: str
    character_id: int
    corporation_id: int
    corporation_name: str
    alliance_id: Optional[int]
    alliance_name: Optional[str]


class Fat(Schema):
    fleet_name: str
    time: datetime
    
    character: Character
    ship: str
    system: str
    

class Message(Schema):
    message: str