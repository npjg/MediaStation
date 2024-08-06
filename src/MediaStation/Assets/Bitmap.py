
import io
from enum import IntEnum

import self_documenting_struct as struct
from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.Asset.Image import RectangularBitmap
from asset_extraction_framework.Exceptions import BinaryParsingError

from ..Primitives.Datum import Datum

# ATTEMPT TO IMPORT THE C-BASED DECOMPRESSION LIBRARY.
# We will fall back to the pure Python implementation if it doesn't work, but there is easily a 10x slowdown with pure Python.
try:
    import MediaStationBitmapRle
    rle_c_loaded = True
except ImportError:
    print('WARNING: The C bitmap decompression binary is not available on this installation. Bitmaps will not be exported.')
    rle_c_loaded = False

# A base header for a bitmap.
class BitmapHeader:
    # Reads a bitmap header from the binary stream at its current position.
    # \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        self._header_size_in_bytes = Datum(stream).d
        self.dimensions = Datum(stream).d
        self.compression_type = Bitmap.CompressionType(Datum(stream).d)
        # TODO: Figure out what this is.
        # This has something to do with the width of the bitmap but is always a few pixels off from the width. 
        # And in rare cases it seems to be the true width!
        self.unk2 = Datum(stream).d

    @property
    def _is_compressed(self) -> bool:
        return (self.compression_type != Bitmap.CompressionType.UNCOMPRESSED) and \
            (self.compression_type != Bitmap.CompressionType.UNCOMPRESSED_2)

# A single, still bitmap.
class Bitmap(RectangularBitmap):
    class CompressionType(IntEnum):
        UNCOMPRESSED = 0
        RLE_COMPRESSED = 1
        UNCOMPRESSED_2 = 7
        UNK1 = 6

    # Reads a bitmap from the binary stream at its current position.
    # \param[in] stream - A binary stream that supports the read method.
    # \param[in] dimensions - The dimensions of the image, if they are known beforehand
    # (like in an asset header). Otherwise, the dimensions will be read from the image.
    def __init__(self, chunk, header_class = BitmapHeader):
        super().__init__()
        self.name = None
        self.header = header_class(chunk)
        self._width = self.header.dimensions.x
        self._height = self.header.dimensions.y
        self.should_export = True

        # READ THE RAW IMAGE DATA.
        self._data_start_pointer = chunk.stream.tell()
        if self.header._is_compressed:
            # READ THE COMPRESSED IMAGE DATA.
            # That will be decompressed later on request.
            self._compressed_image_data_size = chunk.bytes_remaining_count
            self._raw = chunk.read(chunk.bytes_remaining_count)
        else:
            # READ THE UNCOMPRESSED IMAGE DIRECTLY.
            first_bitmap_bytes = chunk.read(2)
            if first_bitmap_bytes != b'\x00\x00':
                raise BinaryParsingError(f'First two bitmap bytes were {first_bitmap_bytes}, not 00 00', chunk.stream)
            self._pixels = chunk.read(chunk.bytes_remaining_count)

            # VERIFY THAT THE WIDTH IS CORRECT.
            if len(self._pixels) != (self._width * self._height):
               # TODO: This was to enable
               # Hunchback:346.CXT:img_q13_BackgroundPanelA to export properly. 
               # It turns out the true width was in fact what's in the header rather than what's actually stored in the width. 
               # I don't know the other cases where this might happen, or what regressions might be caused. 
               if len(self._pixels) == (self.header.unk2 * self._height):
                   self._width = self.header.unk2
                   print(f'WARNING: Found and corrected mismatched width in uncompressed bitmap. Header: {self.header.unk2}. Width: {self._width}. Resetting width to header.')
               else:
                   print(f'WARNING: Found mismatched width in uncompressed bitmap. Header: {self.header.unk2}. Width: {self._width}. This image might not be exported correctly.')

    # Calculates the total number of bytes the uncompressed image (pixels) should occupy, rounded up to the closest whole byte.
    @property
    def _expected_bitmap_length_in_bytes(self) -> int:
        return self.width * self.height

    def export(self, root_directory_path: str, command_line_arguments):
        if self.pixels is not None:
            # DO THE EXPORT.
            super().export(root_directory_path, command_line_arguments)

    def decompress_bitmap(self):
        self._pixels = MediaStationBitmapRle.decompress(self._raw, self.width, self.height)

    # \return The decompressed pixels that represent this image. 
    # The number of bytes is the same as the product of the width and the height.
    @property
    def pixels(self) -> bytes:
        if self._pixels is None:
            if self._compressed_image_data_size > 0:
                if self.header.compression_type == Bitmap.CompressionType.RLE_COMPRESSED:
                    # DECOMPRESS THE BITMAP.
                    if rle_c_loaded:
                        self.decompress_bitmap()

                else:
                    # ISSUE A WARNING.
                    # We can't handle this other compression type yet.
                    print(f'WARNING: ({self.name}) Encountered unhandled bitmap compression type: {self.header.compression_type}. This bitmap will be skipped.')
                    self.should_export = False

        return self._pixels
