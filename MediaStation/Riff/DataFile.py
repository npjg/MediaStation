
from asset_extraction_framework.File import File
from asset_extraction_framework.Asserts import assert_equal

import self_documenting_struct as struct

from .SubFile import SubFile
from .Chunk import ChunkMetadata

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

        # READ THE FIRST SUBFILE.
        self.current_subfile: SubFile = self.read_subfile_metadata()

    ## Reads metadata for the next RIFF subfile from the binary stream at the current position.
    ##
    ## The actual data in the subfile is not read, but the stream position is put at the exact start 
    ## of the FourCC of the first data chunk of this subfile.
    def read_subfile_metadata(self) -> SubFile:
        # ENFORCE PADDING ON THE DWORD BOUNDARY.
        if self.stream.tell() % 2 == 1:
            self.stream.read(1)

        # RETURN THE SUBFILE.
        subfile = SubFile(self.stream)
        self.current_subfile = subfile
        return subfile