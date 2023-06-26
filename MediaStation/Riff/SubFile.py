

from typing import Optional

import self_documenting_struct as struct
from asset_extraction_framework.Asserts import assert_equal

from .Chunk import ChunkMetadata

## A single RIFF-style subfile inside a Media Station data file.
## All subfiles follow this beginning structure:
## - RIFF
##  - IMTSrate (always 4 bytes of data)
##  - LIST
##   - data[fourcc] (e.g. "dataigod" or "dataa000")
##   - [fourcc] (e.g. "igod" or "a000")
##   - [fourcc]
##   - ...
## The real data is stored in the subchunks of the LIST chunk - the "data chunks".
##
## Each of these subfiles are *almost* RIFF files but for one exception:
##  - Some FourCCs are not four characters long; they are actually 8 characters long.
##    The strings "IMTSrate" and "dataigod" are the most common 8-character FourCCs.
##    These cannot be LIST-like structures because there is no size between the 
##    two FourCCs as would be expected for a LIST structure.
class SubFile:
    ## Initializes a subfile from a binary stream at its current position.
    ## After this function runs, the stream position is exactly at the start
    ## of the FourCC of the first data chunk.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # VERIFY THE FILE SIGNATURE.
        self.stream = stream
        self.root_chunk: ChunkMetadata = self.read_chunk_metadata()
        assert_equal(self.root_chunk.fourcc, 'RIFF', 'subfile signature')

        # READ THE EXTRA-LONG FOURCC.
        # The FourCC for the next chunk is actually an "EightCC".
        # It is eight characters long - "IMTSrate". To simplify handling,
        # we will read the first four characters now.
        assert_equal(stream.read(4), b'IMTS', 'subfile signature')

        # READ THE RATE CHUNK.
        # This chunk shoudl always contain just one piece of data - the "rate"
        # (whatever that is). Usually it is zero.
        # TODO: Figure out what this actually is.
        self.read_chunk_metadata()
        self.rate = struct.unpack.uint32_le(stream)

        # READ PAST THE LIST CHUNK.
        # This is the LIST chunk itself - no subchunks or data.
        # We do not care about this chunk itself - the subchunks
        # are what really matters. So we will just read the LIST
        # chunk's metadata and throw it away.
        self.read_chunk_metadata()
        
        # QUEUE UP THE FIRST DATA CHUNK.
        # Client code should read the chunks itself, so we
        # will position the stream right before the first data chunk.
        # That is, the first subchunk of the LIST chunk described above.
        # 
        # The FourCC for this chunk is actually an "EightCC".
        # It is eight characters long - first four for the literal string 'data'
        # and four for the FourCC of the first chunk. To simplify handling,
        # we will read the first for characters now.
        assert_equal(stream.read(4), b'data', 'subfile signature')
        self.current_chunk = None
    
    ## Reads the FourCC and size (collectively, the "metdata") of a RIFF-style chunk 
    ## from the binary stream at the current position.
    ## The binary stream is left at the start of the data for this chunk.
    ## \param[in] fourcc_length - The length, in bytes, of the FourCC to read.
    def read_chunk_metadata(self, fourcc_length = 4) -> Optional[ChunkMetadata]:
        # ENFORCE PADDING ON THE DWORD BOUNDARY.
        if self.stream.tell() % 2 == 1:
            self.stream.read(1)

        # READ THE METADATA FOR THIS CHUNK.
        self.current_chunk = ChunkMetadata(self.stream, fourcc_length)
        return self.current_chunk

    ## \return False if the stream's current position is before the end
    ## of this subfile; True otherwise.
    @property
    def end_of_subfile(self) -> bool:
        return self.stream.tell() >= self.root_chunk.end_pointer