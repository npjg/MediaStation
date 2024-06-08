
from enum import IntEnum

from asset_extraction_framework.Asset.Sound import Sound as BaseSound
from asset_extraction_framework.Asserts import assert_equal

from .. import global_variables
from ..Primitives.Datum import Datum

# ATTEMPT TO IMPORT THE C-BASED DECOMPRESSION LIBRARY.
# We will fall back to the pure Python implementation if it doesn't work, but there is easily a 
# 10x slowdown with pure Python.
try:
    import MediaStationImaAdpcm
    adpcm_c_loaded = True
except ImportError:
    print('WARNING: The C decompression binary is not available on this installation. Any IMA ADPCM-encoded audio will not be exported.')
    adpcm_c_loaded = False
    raise

class Sound(BaseSound):
    ## Reads a sound from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] header - The header for this asset.
    def __init__(self, audio_encoding):
        super().__init__()
        self._signed = True
        self._big_endian = False
        self._sample_width = 2 # 16 bits
        self._audio_encoding = audio_encoding
        self._chunks = []
        if self._audio_encoding == 0x0010:
            # Uncompressed PCM
            self._sample_rate = 22050
            self._channel_count = 1

        elif self._audio_encoding == 0x0004:
            # IMA ADPCM
            # TODO: This audio encoding is not quite correct.
            # The raw ffmpeg encoding that sounds the best is adpcm_ima_ws
            # at mono 22050 Hz (s16le) but even that is not quite right! 
            self._sample_rate = 22050
            self._channel_count = 1

        else: 
            raise ValueError(f'Received unknown sound encoding specifier: 0x{self.audio_encoding:04x}')

    ## Reads a sound in a subfile.
    ## \param[in] subfile - The subfile to read. The binary stream must generally
    ## be at the start of the subfile.
    def read_subfile(self, subfile, chunk, total_chunks):
        self._chunk_count = total_chunks
        asset_id = chunk.fourcc

        self.read_chunk(chunk)
        for _ in range(self._chunk_count - 1):
            chunk = subfile.get_next_chunk()
            assert_equal(chunk.fourcc, asset_id, "sound chunk label")
            self.read_chunk(chunk)

    ##  Reads one chunk of a sound from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def read_chunk(self, chunk):
        # TODO: Update to use the memview interface to avoid copying.
        samples = chunk.read(chunk.length)
        self._chunks.append(samples)

    @property
    def pcm(self):
        if self._pcm is None:
            self._pcm = bytearray()
            if self._audio_encoding == 0x0010:
                for pcm_chunk in self._chunks:
                    self._pcm.extend(pcm_chunk)

            elif self._audio_encoding == 0x0004:
                for adpcm_chunk in self._chunks:
                    decoded_pcm = MediaStationImaAdpcm.decode(adpcm_chunk)
                    self._pcm.extend(decoded_pcm)

        return self._pcm


