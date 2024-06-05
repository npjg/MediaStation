from enum import IntEnum

import self_documenting_struct as struct
from asset_extraction_framework.Exceptions import BinaryParsingError

from .BoundingBox import BoundingBox
from .Polygon import Polygon
from .Point import Point
from .Reference import Reference

## Except for compressed image data and audio data,
## nearly all data in Media Station files is encapsulated 
## in "datums", so called because they generally represent 
## the smallest units of useful data in Media Station data files. 
## 
## A datum provides a 16-bit type code, followed by a variable-
## length data section, whose length is generally defined 
## by the type code. 
## Here is an example, where `xx` represents one byte:
##  Type code
##  |     Data
##  |     | 
##  xx xx xx xx .. xx xx
## TODO: Add type assertions for extra checking.
class Datum:
    ## The various known datum type codes.
    class Type(IntEnum):
        # These are numeric types.
        UINT8 = 0x0002
        # TODO: Understand why there are different (u)int16 type codes.
        UINT16_1 = 0x0003
        UINT16_2 = 0x0013
        INT16_1 = 0x0006
        INT16_2 = 0x0010
        # TODO: Understand why there are two different uint32 type codes.
        UINT32_1 = 0x0004
        UINT32_2 = 0x0007
        # TODO: Understand why there are two different float64 type codes.
        FLOAT64_1 = 0x0011
        FLOAT64_2 = 0x0009
        # These are string types.
        STRING = 0x0012
        FILENAME = 0x000a
        # These are geometric types. 
        POINT_1 = 0x000f
        POINT_2 = 0x000e
        BOUNDING_BOX = 0x000d
        POLYGON = 0x001d
        # These are other types.
        PALETTE = 0x05aa
        REFERENCE = 0x001b

    ## Reads a datum from the binary stream at its current position.
    ## The number of bytes read from the stream depends on the type
    ## of the datum.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # READ THE TYPE OF THE DATUM. 
        # Regardless of the datum's value the type always has constant size.
        self.t = struct.unpack.uint16_le(stream)

        # READ THE VALUE IN THE DATUM.
        if (self.t == Datum.Type.UINT8):
            self.d = struct.unpack.uint8(stream)

        elif (self.t == Datum.Type.UINT16_1) or (self.t == Datum.Type.UINT16_2):
            self.d = struct.unpack.uint16_le(stream)

        elif (self.t == Datum.Type.INT16_1) or (self.t == Datum.Type.INT16_2):
            self.d = struct.unpack.int16_le(stream)

        elif (self.t == Datum.Type.UINT32_1) or (self.t == Datum.Type.UINT32_2):
            self.d = struct.unpack.uint32_le(stream)

        elif (self.t == Datum.Type.FLOAT64_1) or (self.t == Datum.Type.FLOAT64_2):
            self.d = struct.unpack.raw("<d", stream.read(8))[0]

        elif (self.t == Datum.Type.STRING) or (self.t == Datum.Type.FILENAME):
            # TODO: Check titles in languages to see if there are any
            # non-ASCII characters.
            size = Datum(stream).d
            self.d = stream.read(size).decode('ascii')

        elif (self.t == Datum.Type.BOUNDING_BOX):
            self.d = BoundingBox(stream)

        elif (self.t == Datum.Type.POINT_1) or (self.t == Datum.Type.POINT_2):
            self.d = Point(stream)
             
        elif (self.t == Datum.Type.POLYGON):
            self.d = Polygon(stream)

        elif (self.t == Datum.Type.REFERENCE):
            self.d = Reference(stream)

        else:
            raise BinaryParsingError(f'Unknown datum type: 0x{self.t:04x}', stream)