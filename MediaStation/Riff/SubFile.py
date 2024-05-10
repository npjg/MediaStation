

from typing import Optional

import self_documenting_struct as struct
from asset_extraction_framework.Exceptions import BinaryParsingError
from asset_extraction_framework.Asserts import assert_equal

from .Chunk import Chunk

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
        self.root_chunk: Chunk = self.get_next_chunk(called_from_init = True)
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
        self.get_next_chunk()
        self.rate = struct.unpack.uint32_le(stream)

        # READ PAST THE LIST CHUNK.
        # This is the LIST chunk itself - no subchunks or data.
        # We do not care about this chunk itself - the subchunks
        # are what really matters. So we will just read the LIST
        # chunk's metadata and throw it away.
        self.get_next_chunk()
        
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
    
    ## Reads the FourCC and size (collectively, the "metadata") of a RIFF-style chunk 
    ## from the binary stream at the current position.
    ## The binary stream is left at the start of the data for this chunk.
    ## \param[in] fourcc_length - The length, in bytes, of the FourCC to read.
    def get_next_chunk(self, fourcc_length = 4, called_from_init = False) -> Optional[Chunk]:
        # VERIFY WE WILL NOT GET A CHUNK PAST THE END OF THE SUBFILE.
        if not called_from_init:
            MINIMUM_BYTES_FOR_SUBFILE = 8
            new_end_pointer = self.stream.tell() + MINIMUM_BYTES_FOR_SUBFILE
            attempted_read_past_end_of_subfile =  (new_end_pointer > self.root_chunk.end_pointer)
            if attempted_read_past_end_of_subfile:
                bytes_past_chunk_end = new_end_pointer - self.root_chunk.end_pointer
                raise BinaryParsingError(
                    f'Attempted to read a new chunk past the end of the subfile whose data starts at 0x{self.root_chunk.data_start_pointer:02x} and ends at 0x{self.root_chunk.end_pointer:02x}.',
                    self.stream)

        # GET THE NEXT CHUNK.
        # Padding should be enforced so the next chunk starts on an even-indexed byte.
        stream_position_is_odd = (self.stream.tell() % 2 == 1)
        if stream_position_is_odd:
            # So, for example, if we are currently at 0x701, the next chunk actually 
            # starts at 0x702, so we need to throw away the byte at 0x701.
            # TODO: Verify the thrown-away byte is always zero.
            self.stream.read(1)
        self.current_chunk = Chunk(self.stream, fourcc_length)
        return self.current_chunk

    ## Skips over the entire subfile. The stream is left pointing to the 
    ## next subfile, and any bytes in the subfile not yet read are discarded.
    def skip(self):
        bytes_remaining_in_subfile = self.root_chunk.end_pointer - self.stream.tell()
        self.stream.read(bytes_remaining_in_subfile)
        if not self.at_end:
            self.stream.read(1)

    ## \return False if the stream's current position is before the end
    ## of this subfile; True otherwise.
    @property
    def at_end(self) -> bool:
        stream_position_is_odd = (self.stream.tell() % 2 == 1)
        if stream_position_is_odd:
            # In Media Station data files, there is no meaningful data that can be stored
            # in a single byte. So if the stream position is odd, it is possible that
            # one byte is just a padding byte. Thus, the effective length of the subfile
            # should be shortened by one.
            return self.stream.tell() >= (self.root_chunk.end_pointer - 1)
        return self.stream.tell() >= (self.root_chunk.end_pointer)