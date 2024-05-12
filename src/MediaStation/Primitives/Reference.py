
## Holds a reference to a data chunk. This data chunk 
## is usually in the same file as this reference,
## but this is not always the case.
## \param[in] stream - A binary stream that supports the read method.
class Reference:
    ## Reads a reference from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        ## The FourCC of the referenced chunk.
        ## This is usually something like "a123".
        ## This chunk ID is unique in the game.
        self.chunk_id = stream.read(4).decode('ascii')
 
    ## \return The integral part of the chunk reference
    ## as a hexadecimal integer. 
    ## 
    ## For instance, if the referenced chunk ID was "a123",
    ## the integer 0x123 would be returned.
    def as_int(self) -> int:
        return int(self.chunk_id[1:], 16)