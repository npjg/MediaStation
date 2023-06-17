
import self_documenting_struct as struct

from . import Datum

## A two-dimensional point (X, Y).
class Point:
    def __init__(self, stream, **kwargs):
        COORDINATE_SEPARATOR = b'\x10\x00'
        if stream:
            # READ THE COORDINATES.
            # These should be signed 16-bit integers.
            self.x = Datum.Datum(stream).d
            self.y = Datum.Datum(stream).d
        else:
            self.x = kwargs.get("x")
            self.y = kwargs.get("y")
