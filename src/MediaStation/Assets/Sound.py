
from enum import IntEnum

from asset_extraction_framework.Asset.Sound import Sound as BaseSound
from asset_extraction_framework.Asserts import assert_equal

# ATTEMPT TO IMPORT THE C-BASED DECOMPRESSION LIBRARY.
# TODO: A pure Python implementation of the IMA ADPCM decoder currently doesn't
# exist. Even if it's really slow, it probably should exist as a fallback.
try:
    import MediaStationImaAdpcm
    adpcm_c_loaded = True
except ImportError:
    print('WARNING: The C decompression binary is not available on this installation. Any IMA ADPCM-encoded audio (mostly ambient sounds) will not be exported.')
    adpcm_c_loaded = False
    raise

class Sound(BaseSound):
    class Encoding(IntEnum):
        PCM_S16LE_MONO_22050 = 0x0010 # Uncompressed linear PCM
        IMA_ADPCM_S16LE_MONO_22050 = 0x0004 # IMA ADPCM encoding, must be decoded

    ## Reads a sound from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] header - The header for this asset.
    def __init__(self, sound_encoding):
        super().__init__()
        self._signed = True
        self._big_endian = False
        self._sample_width = 2 # 16 bits
        self._audio_encoding = sound_encoding
        self._sample_rate = 22050
        self._channel_count = 1
        # The linear PCM and IMA ADPCM encodings have the same parameters,
        # but they must be decoded separately.
        self._chunks = []

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
            if  Sound.Encoding.PCM_S16LE_MONO_22050 == self._audio_encoding:
                # READ THE LINEAR PCM SAMPLES.
                for pcm_chunk in self._chunks:
                    self._pcm.extend(pcm_chunk)

            elif Sound.Encoding.IMA_ADPCM_S16LE_MONO_22050 == self._audio_encoding:
                # DECODE THE IMA ADPCM INTO LINEAR ADPCM SAMPLES.
                for adpcm_chunk in self._chunks:
                    # TODO: Determine if the IMA ADPCM is the Microsoft flavor.
                    # At any rate, each chunk MUST be decoded independently for 
                    # the decoded audio to have the correct volume all the way 
                    # through. Decoding all chunks at once leads to jumps in 
                    # volume about every 0.6 seconds.
                    decoded_pcm = MediaStationImaAdpcm.decode(adpcm_chunk)
                    self._pcm.extend(decoded_pcm)

        return self._pcm


