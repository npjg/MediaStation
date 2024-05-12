
from asset_extraction_framework.Asserts import assert_equal

from .. import global_variables
from ..Primitives.Datum import Datum

## A compiled script function that executes in the Media Station bytecode interpreter.
## TODO: Currently the bytecode structure can be parsed, but I haven't had
## much success actualy decompiling it yet. This will be a big effort I think.
##
## Newer titles have very little bytecode but earlier titles have a lot.
## It seems that the scripting for newer titles is baked into the executable.
class Script:
    ## Reads a compiled script from a binary stream at is current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] in_independent_asset_chunk - When True, the function to be
    ##            read is not in an asset header but is its own data chunk.
    def __init__(self, chunk, in_independent_asset_chunk):
        # DECLARE THE SCRIPT ID.
        # The script ID is only populated if the script is in its own chunk.
        # If it is instead attached to an asset header, it takes on the ID of that asset.
        self.name = None
        self.id = None

        # DECLARE THE SCRIPT TYPE.
        # This only occurs in scripts that are attached to asset headers.
        # TODO: Understand what this is. I think it says when a given script
        # triggers (like when the asset is clicked, etc.)
        self.type = None

        # READ THE SCRIPT METADATA.
        if in_independent_asset_chunk:
            # VERIFY THE FILE ID.
            # TODO: Actually verify this.
            Datum(chunk)

            # READ THE SCRIPT ID.
            self.id = Datum(chunk).d + 19900
        else:
            # READ THE SCRIPT TYPE.
            self.type = Datum(chunk).d
            self.unk1 = Datum(chunk).d

            # READ THE SCRIPT SIZE.
            # This is not actually used in the decompilation code, but I have given it a proper name anyway.
            self.size = Datum(chunk).d

        self._code = CodeChunk(chunk.stream)
        if in_independent_asset_chunk and not global_variables.version.is_first_generation_engine:
            assert_equal(Datum(chunk).d, 0x00, "end-of-chunk flag")

    ## TODO: Export these to individual JSONs rather than putting them in the 
    ## main JSON export (that will make analyzing them much easier!)
    def export(self, root_directory_path, command_line_arguments):
        return

## TODO: Is this a whole function, or is it something else?
class CodeChunk:
    def __init__(self, stream, length_in_bytes = None):
        self._stream = stream
        if not length_in_bytes:
            self._length_in_bytes = Datum(stream).d
        else:
            self._length_in_bytes = length_in_bytes
        self._start_pointer = stream.tell()
        self.statements = []
        while not self._at_end:
            statement = self.read_statement(stream)
            self.statements.append(statement)

    @property
    def _end_pointer(self):
        return self._start_pointer + self._length_in_bytes

    @property
    def _at_end(self):
        return self._stream.tell() >= self._end_pointer

    # This is a recursive function that builds a statement.
    # Statement probably isn't ths best term, since statements can contain other statements. 
    # And I don't want to imply that it is some sort of atomic thing. 
    ## \param[in] stream - A binary stream at the start of the statement.
    ## \param[in] string_reading_enabled - True if seeing the section type for a string indicates 
    ##            that a string should be read. Strings seem to be present in only a few files
    ##            in Dalmatians, and it is difficult to predict where they will appear.
    def read_statement(self, stream, string_reading_enabled = False):
        section_type = Datum(stream)
        if (Datum.Type.UINT32_1 == section_type.t):
            return CodeChunk(stream, section_type.d)

        iteratively_built_statement = []
        if section_type.d == 0x0067:
            for _ in range(3):
                statement = self.read_statement(stream)
                iteratively_built_statement.append(statement)
                if self._at_end:
                    break

        elif section_type.d == 0x0066:
            for index in range(2):
                ## I haven't figured out another heuristic to determine when
                ## the datum is a literal or when it is the prefix for a string.
                string_reading_enabled = (index == 0)
                statement = self.read_statement(stream, string_reading_enabled = string_reading_enabled)
                iteratively_built_statement.append(statement)
                if self._at_end:
                    break

        elif section_type.d == 0x0065:
            statement = self.read_statement(stream)
            iteratively_built_statement.append(statement)

        elif section_type.d == 0x009a and string_reading_enabled: # character string
            string_length = Datum(stream).d
            iteratively_built_statement = stream.read(string_length).decode('latin-1')

        else:
            iteratively_built_statement = section_type.d

        return iteratively_built_statement