
from dataclasses import dataclass
from enum import IntEnum

## There are three possible text justification settings.
class Justification(IntEnum):
    LEFT   = 0x025c,
    RIGHT  = 0x025d,
    CENTER = 0x025e,

## The text-related settings that can define an asset.
## This does not accept a stream because all the reading 
## is done through the asset header loop.
@dataclass
class Text:
    font: str = None
    initial_text: str = None
    maximum_width: int = None
    justification: Justification = None