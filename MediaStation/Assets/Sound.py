
from enum import IntEnum

from asset_extraction_framework.Asset.Sound import Sound as BaseSound
from asset_extraction_framework.Asserts import assert_equal

from .. import global_variables

from ..Primitives.Datum import Datum

            # if self.encoding and self.encoding == 0x0010:
            #     command = ['ffmpeg', '-y', '-f', 's16le', '-ar', '11.025k', '-ac', '2', '-i', 'pipe:', filename]
            # elif self.encoding and self.encoding == 0x0004:
            #     # TODO: Fine the proper codec. This ALMOST sounds right.
            #     command = ['ffmpeg', '-y', '-f', 's16le', '-ar', '22.050k', '-ac', '1', "-acodec", "adpcm_ima_ws", '-i', 'pipe:', filename]
            # else:
            #     raise ValueError("Sound.export(): Received unknown encoding specifier: 0x{:04x}.".format(self.encoding))
            #     command = ['ffmpeg', '-y', '-f', 's16le', '-ar', '11.025k', '-ac', '2', '-i', 'pipe:', filename]

class Sound(BaseSound):
    ## Reads a sound from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] header - The header for this asset.
    def __init__(self, audio_encoding):
        super().__init__()
        self._pcm = bytearray()
        self._signed = True
        self._big_endian = False
        self._sample_width = 2
        if audio_encoding == 0x0010:
            self._sample_rate = 11025
            self._channel_count = 2
        elif audio_encoding == 0x0004:
            self._sample_rate = 22050
            self._channel_count = 1
        else: 
            print (f'Sound.export(): Received unknown encoding specifier: 0x{audio_encoding:04x}.')

    ## Reads a sound in a subfile.
    ## \param[in] subfile - The subfile to read. The binary stream must generally
    ## be at the start of the subfile.
    def read_subfile(self, subfile, total_chunks):
        self._chunk_count = total_chunks
        asset_id = subfile.current_chunk.fourcc

        self.read_chunk(subfile.stream, subfile.current_chunk.length)
        for index in range(self._chunk_count - 1):
            subfile.read_chunk_metadata()
            assert_equal(subfile.current_chunk.fourcc, asset_id, "sound chunk label")
            self.read_chunk(subfile.stream, subfile.current_chunk.length)

    ##  Reads one chunk of a sound from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] length - 
    def read_chunk(self, stream, length):
        # TODO: Update to use the memview interface to avoid copying.
        # self.chunks.append(stream.read(length))
        self._pcm.extend(stream.read(length))
