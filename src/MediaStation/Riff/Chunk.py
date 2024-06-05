
import self_documenting_struct as struct
from asset_extraction_framework.Exceptions import BinaryParsingError

from asset_extraction_framework.Asserts import assert_equal

## DEFINE CHUNK-RELATED ERRORS.
# TODO: Should this inherit from BinaryParsingError so we get a nice
# hexdump when it is raised?
class ZeroLengthChunkError(Exception):
    pass

## Media Station data files are *almost* RIFF files, but not quite. 
## Here are the major differences:
##  - Each Media Station file contains one or more RIFF files after an (optional) header.
##  - Some FourCCs are not four characters long; they are actually 8 characters long.
##    The strings "IMTSrate" and "dataigod" are the most common 8-character FourCCs.
##    These cannot be LIST-like structures because there is no size between the 
##    two FourCCs as would be expected for a LIST structure.
class Chunk:
    def __init__(self, stream, fourcc_length = 4):
        self.stream = stream
        self.fourcc = stream.read(fourcc_length).decode('ascii')
        self.length = struct.unpack.uint32_le(stream)
        if self.length == 0:
            raise ZeroLengthChunkError('Encountered a zero-length chunk. This usually indicates corrupted data - maybe a CD-ROM read error.')
        self.data_start_pointer = stream.tell()

    ## Skips over the entire chunk. The stream is left pointing to the 
    ## next chunk/subfile, and any bytes in the chunk not yet read are discarded.
    def skip(self):
        bytes_remaining_in_chunk = self.end_pointer - self.stream.tell()
        self.stream.read(bytes_remaining_in_chunk)

    ## Reads the given number of bytes from the chunk, or throws an error if there is an attempt
    ## to read past the end of the chunk. Generally this is the only byte reading method that should
    ## be called directly because it includes this protection.
    ##
    ## To make client code more self-documenting, the read() method with no number of bytes provided
    ## is deliberately not supported. A byte count must be provided, for instance:
    ##  chunk.read(chunk.bytes_remaining_count)
    def read(self, number_of_bytes) -> bytes:
        # VERIFY WE WILL NOT READ PAST THE END OF THE CHUNK.
        new_end_pointer = self.stream.tell() + number_of_bytes
        attempted_read_past_end_of_chunk = (new_end_pointer > self.end_pointer)
        if attempted_read_past_end_of_chunk:
            bytes_past_chunk_end =  new_end_pointer - self.end_pointer
            raise BinaryParsingError(
                f'Attempted to read {bytes_past_chunk_end} bytes past end of chunk "{self.fourcc}". Attempted read started at 0x{self.stream.tell():02x}.',
                self.stream)
        
        # READ THE REQUESTED DATA.
        return self.stream.read(number_of_bytes)

    ## \return The total number of data bytes consumed from this chunk 
    ## (not including the bytes for the FourCC and chunk length).
    @property 
    def bytes_consumed_count(self) -> int:
        return self.stream.tell() - self.data_start_pointer

    ## \return The total number of bytes remaining until the end of the 
    ## data in this chunk.
    @property
    def bytes_remaining_count(self) -> int:
        return self.end_pointer - self.stream.tell()

    ## \return Whether or not this chunk is an "igod" chunk.
    ## Chunks like these store mainly header information.
    ## TODO: Document what "igod" means.
    @property
    def is_igod(self) -> bool:
        return (self.fourcc == 'igod')

    ## \return True if all the data in this chunk has been read;
    ## False otherwise.
    @property
    def at_end(self) -> bool:
        return (self.stream.tell() >= self.end_pointer)

    ## \return The absolute offset in the current file where the data for this chunk ends.
    @property
    def end_pointer(self) -> int:
        return self.data_start_pointer + self.length

    ## Parses the a000-style FourCCs into integers.
    @property
    def chunk_integer(self):
        HEXADECIMAL_BASE = 16
        hex_number_as_string = self.fourcc[1:]
        return int(hex_number_as_string, HEXADECIMAL_BASE)
