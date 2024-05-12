
import self_documenting_struct as struct

from . import Datum

## A rectangle defined as a series of two-dimensional points.
class BoundingBox:
    def __init__(self, stream):
        self.left_top_point = Datum.Datum(stream).d
        self.dimensions = Datum.Datum(stream).d