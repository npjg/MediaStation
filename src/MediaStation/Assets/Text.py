
from enum import IntEnum
from typing import List

from ..Primitives.Datum import Datum

## Similar to a regex character class (e.g. `[A-Z]`).
## Defines a contiguous range of ASCII characters
## based on the ASCII code of the first and last 
## characters, inclusive.
class CharacterClass:
    def __init__(self, chunk):
        self.first_ascii_code = Datum(chunk).d
        self.last_ascii_code = Datum(chunk).d

    @property
    def first_character(self):
        return chr(self.first_ascii_code)
    
    @property
    def last_character(self):
        return chr(self.last_ascii_code)

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
# TODO: Actually read the whole text object in here.
class Text:
    def __init__(self):
        self.font: str = None
        self.initial_text: str = None
        self.max_length: int = None
        self.justification: Justification = None
        self.position: Position = None
        self.accepted_input = []
