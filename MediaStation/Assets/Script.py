
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
            self.id = Datum(chunk).d
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

class CodeChunk:
    def __init__(self, stream, length_in_bytes = None):
        self.stream = stream
        if not length_in_bytes:
            self.length_in_bytes = Datum(stream).d
        else:
            self.length_in_bytes = length_in_bytes
        self.start_pointer = stream.tell()
        self.statements = []
        while not self.at_end:
            statement = self.read_statement(stream)
            self.statements.append(statement)

    @property
    def end_pointer(self):
        return self.start_pointer + self.length_in_bytes

    @property
    def at_end(self):
        return self.stream.tell() >= self.end_pointer

    def read_statement(self, stream, string = False):
        section_type = Datum(stream)
        if (Datum.Type.UINT32_1 == section_type.t):
            return CodeChunk(stream, section_type.d)

        code = []
        if section_type.d == 0x0067:
            for _ in range(3):
                statement = self.read_statement(stream)
                code.append(statement)
                if self.at_end:
                    break

        elif section_type.d == 0x0066:
            for i in range(2):
                statement = self.read_statement(stream, string = not i)
                code.append(statement)
                if self.at_end:
                    break

        elif section_type.d == 0x0065:
            statement = self.read_statement(stream)
            code.append(statement)

        elif section_type.d == 0x009a and string: # character string
            size = Datum(stream)
            code = stream.read(size.d).decode('latin-1')
            
        else:
            code = section_type.d

        return code