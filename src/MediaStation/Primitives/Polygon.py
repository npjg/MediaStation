
import self_documenting_struct as struct

from . import Datum
from .Point import Point

## A polygon defined as a series of two-dimensional points.
## Generally used for defining the clickable and 
## highlightable regions of sprites, which need more 
## exact specification than a single rectangle.
class Polygon:
    def __init__(self, stream):
        # READ THE TOTAL NUMBER OF POINTS IN THIS POLYGON.
        total_points = Datum.Datum(stream).d

        # READ THESE POINTS.
        self.points = []
        for _ in range(total_points):
            # TODO: Define what this separator is to 
            # provide more rigorous parsing.
            stream.read(2)
            self.points.append(Point(stream))
