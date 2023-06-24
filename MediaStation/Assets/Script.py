
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
    def __init__(self, stream, in_independent_asset_chunk):
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
            Datum(stream)

            # READ THE SCRIPT ID.
            self.id = Datum(stream).d
        else:
            # READ THE SCRIPT TYPE.
            self.type = Datum(stream).d
            self.unk1 = Datum(stream).d

            # READ THE SCRIPT SIZE.
            # This is not actually used in the decompilation code, but I have given it a proper name anyway.
            self.size = Datum(stream).d

        start = stream.tell()
        initial = Datum(stream)
        
        self._code = self.chunk(initial, stream)
        assert_equal(stream.tell() - start - 0x006, self._code["sz"].d, "length")
        if in_independent_asset_chunk and not global_variables.old_generation:
            assert_equal(Datum(stream).d, 0x00, "end-of-chunk flag")

    def chunk(self, size, stream):
        code = {"sz": size, "ch": []}
        start = stream.tell()
        while stream.tell() - start < size.d:
            code["ch"].append(self.entity(Datum(stream), stream, end=start+size.d))

        return code

    def entity(self, token, stream, end, string=False):
        if token.t == 0x0004:
            return self.chunk(token, stream)

        code = []
        if token.d == 0x0067:
            for _ in range(3):
                if len(code) > 0 and isinstance(code[0], Datum) and code[0].d == 203:
                    code.append(Datum(stream))
                else:
                    code.append(self.entity(Datum(stream), stream, end))
                if stream.tell() >= end:
                    break
        elif token.d == 0x0066:
            for i in range(2):
                code.append(self.entity(Datum(stream), stream, end, string=not i))
                if stream.tell() >= end:
                    break
        elif token.d == 0x0065:
            code.append(Datum(stream))
            # code.append(self.entity(Datum(stream), stream, end))
        elif token.d == 0x009a and string: # character string
            size = Datum(stream)
            code = stream.read(size.d).decode("utf-8")
        else:
            code = token

        return code