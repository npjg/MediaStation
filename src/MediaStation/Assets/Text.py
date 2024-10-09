
from dataclasses import dataclass
from enum import IntEnum

## The horizontal alignment of the text.
class Justification(IntEnum):
    LEFT   = 0x025c
    RIGHT  = 0x025d
    CENTER = 0x025e

## The vertical alignment of the text.
class Position(IntEnum):
    MIDDLE = 0x025e
    TOP = 0x0260
    BOTTOM = 0x0261

## The text-related settings that can define an asset.
## This does not accept a stream because all the reading 
## is done through the asset header loop.
@dataclass
class Text:
    font: str = None
    initial_text: str = None
    max_length: int = None
    justification: Justification = None
    position: Position = None