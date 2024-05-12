
from enum import IntEnum

from asset_extraction_framework.Asset.Sound import Sound as BaseSound
from asset_extraction_framework.Asserts import assert_equal

from .. import global_variables
from ..Primitives.Datum import Datum

class Sound(BaseSound):
    ## Reads a sound from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] header - The header for this asset.
    def __init__(self, audio_encoding):
        super().__init__()
        self._pcm = bytearray()
        self._signed = True
        self._big_endian = False
        self._sample_width = 2 # 16 bits
        if audio_encoding == 0x0010:
            self._sample_rate = 22050
            self._channel_count = 1
        elif audio_encoding == 0x0004:
            # TODO: This audio encoding is not quite correct.
            # The raw ffmpeg encoding that sounds the best is adpcm_ima_ws
            # at mono 22050 Hz (s16le) but even that is not quite right! 
            # There is some weirdness going on here for sure!
            self._sample_rate = 22050
            self._channel_count = 1
        else: 
            raise ValueError(f'Received unknown sound encoding specifier: 0x{audio_encoding:04x}')

    ## Reads a sound in a subfile.
    ## \param[in] subfile - The subfile to read. The binary stream must generally
    ## be at the start of the subfile.
    def read_subfile(self, subfile, chunk, total_chunks):
        self._chunk_count = total_chunks
        asset_id = chunk.fourcc

        self.read_chunk(chunk)
        for index in range(self._chunk_count - 1):
            chunk = subfile.get_next_chunk()
            assert_equal(chunk.fourcc, asset_id, "sound chunk label")
            self.read_chunk(chunk)

    ##  Reads one chunk of a sound from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] length - 
    def read_chunk(self, chunk):
        # TODO: Update to use the memview interface to avoid copying.
        self._pcm.extend(chunk.read(chunk.length))
