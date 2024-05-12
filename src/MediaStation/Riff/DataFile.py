
from asset_extraction_framework.File import File
from asset_extraction_framework.Asserts import assert_equal
import self_documenting_struct as struct

from .SubFile import SubFile

## A Media Station data file, which consists of one or more subfiles.
class DataFile(File):
    ## Parses a context from the given path.
    ## \param[in] - filepath: The filepath of the file, if it exists on the filesystem.
    ##                        Defaults to None if not provided.
    ## \param[in] - stream: A BytesIO-like object that holds the file data, if the file does
    ##                      not exist on the filesystem.
    ## NOTE: It is an error to provide both a filepath and a stream, as the source of the data
    ##       is then ambiguous.
    def __init__(self, has_header: bool, filepath: str = None, stream = None):
        # OPEN THE FILE FOR READING.
        super().__init__(filepath, stream)

        # READ THE MEDIA STATION HEADER.
        # In context (CXT) files, there is some header data before the first subfile.
        # The system (STM) files do not have this Media Station header.
        if has_header:
            # READ THE HEADER DATA.
            assert_equal(self.stream.read(4), b'II\x00\x00', 'file signature')
            self.unk1 = struct.unpack.uint32_le(self.stream)
            self.subfile_count = struct.unpack.uint32_le(self.stream)
            # The total size of this file, including this header.
            # (Basically the true file size shown on the filesystem.)
            self.file_size = struct.unpack.uint32_le(self.stream)

            # VERIFY THE FILE IS NOT HEADER-ONLY.
            # Some older titles have files that contain no contents 
            # except for the Media Station header. like this; not sure why.
            if self.stream.tell() == self.file_size:
                # CANCEL READING.
                # Since this file only contains a header, there is no further data to read.
                self.header_only = True
                return
            else:
                self.header_only = False

    ## Reads metadata for the next RIFF subfile from the binary stream at the current position.
    ##
    ## The actual data in the subfile is not read, but the stream position is put at the exact start 
    ## of the FourCC of the first data chunk of this subfile.
    def get_next_subfile(self) -> SubFile:
        # Padding should be enforced so the next subfile starts on an even-indexed byte.
        stream_position_is_odd = self.stream.tell() % 2 == 1
        if stream_position_is_odd:
            # So, for example, if we are currently at 0x701, the next subfile actually 
            # starts at 0x702, so we need to throw away the byte at 0x701.
            # TODO: Verify the thrown-away byte is always zero.
            self.stream.read(1)
        subfile = SubFile(self.stream)
        return subfile
