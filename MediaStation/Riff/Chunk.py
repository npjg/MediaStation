

import self_documenting_struct as struct

from asset_extraction_framework.Asserts import assert_equal

## Media Station data files are *almost* RIFF files, but not quite. 
## Here are the major differences:
##  - Each Media Station file contains one or more RIFF files after an (optional) header.
##  - Some FourCCs are not four characters long; they are actually 8 characters long.
##    The strings "IMTSrate" and "dataigod" are the most common 8-character FourCCs.
##    These cannot be LIST-like structures because there is no size between the 
##    two FourCCs as would be expected for a LIST structure.
class ChunkMetadata:
    def __init__(self, stream, fourcc_length = 4):
        self.start_pointer = stream.tell()
        self.fourcc = stream.read(fourcc_length).decode('ascii')
        self.length = struct.unpack.uint32_le(stream)

    @property
    def end_pointer(self):
        return self.start_pointer + self.length

    @property
    def chunk_integer(self):
        return int(self.fourcc[1:], 16)