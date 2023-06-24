
import io

import self_documenting_struct as struct

from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.Asset.Image import RectangularBitmap
from ..Primitives.Datum import Datum
#import bitmap_decompressor

## A single, still bitmap.
class Bitmap(RectangularBitmap):
    ## Reads a bitmap from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] size - The size (in bytes) of the image ast stored in the binary stream.
    ## \param[in] dimensions - The dimensions of the image, if they are known beforehand
    ##            (like in an asset header). Otherwise, the dimensions will be read
    ##            from the image.
    def __init__(self, stream, length, dimensions = None):
        super().__init__()
        end_pointer = stream.tell() + length
        self._is_compressed: bool = True
        if dimensions is None:
            # READ THE BITMAP HEADER.
            # TODO: Is this first one actually a byte count?
            self.unk1 = Datum(stream).d 
            dimensions = Datum(stream).d
            self._is_compressed = bool(Datum(stream).d)
            self.unk2 = Datum(stream).d
        self._width = dimensions.x
        self._height = dimensions.y

        # Only nonempty for images that have keyframes that need to 
        # intersect 
        self.transparency_region = []

        # READ THE RAW IMAGE DATA.
        image_data_size = end_pointer - stream.tell()
        if self._is_compressed:
            # READ THE COMPRESSED IMAGE DATA.
            # That will be decompressed later on request.
            self._compressed_image_data_size = image_data_size
            self._raw = stream.read(self._compressed_image_data_size)
        else:
            # READ THE UNCOMPRESSED IMAGE DIRECTLY.
            assert stream.read(2) == b'\x00\x00'
            self._pixels = stream.read(image_data_size - 2)

    # Decompresses the RLE-compressed pixel data for this bitmap.
    # The RLE compression algorithm is almost the Microsoft standard algorithm
    # but with a few twists:
    #  - 
    # NOTE: This is a pure Python and has been reimplemented in C for better performance.
    # However, this remains as a reference and as a fallback in case the C implementation
    # is not available.
    def decompress_bitmap(self):
        # TODO: Make this easier to understand.
        # To ask ChatGPT. I am making a decompression algorithm in Python.
        # Yes, I know I should probably write it in C instead, but I am using Python
        # to prototype for now. Anyway, I am creating a bytearray 
        self._pixels = b''
        compressed_image_data = io.BytesIO(self._raw)
        pixels = bytearray((self.width * self.height) * b'\x00')


        #compressed_data = b'\x01\x02\x03...'  # Provide the compressed data
        #pixels = bytearray(width * height)  # Prepare the buffer for decompressed pixels

        #bitmap_decompressor.decompress_bitmap(compressed_data, len(compressed_data), pixels, self.width, self.height)
        #return

        if self._compressed_image_data_size <= 2:
            self._pixels = bytes(pixels)
            return
        if compressed_image_data.read(2) == b'\x00\x00':
            pass
        else:
            compressed_image_data.seek(0)

        # DECOMPRESS THE IMAGE.
        image_fully_read = False
        row_index = 0
        while row_index < self.height:
            horizontal_pixel_offset = 0
            reading_transparency_run = False
            while True:
                operation = struct.unpack.uint8(compressed_image_data)
                if operation == 0x00:
                    # ENTER CONTROL MODE.
                    operation = struct.unpack.uint8(compressed_image_data)
                    if operation == 0x00:
                        # MARK THE END OF THE LINE.
                        break

                    elif operation == 0x01:
                        # MARK THE END OF THE IMAGE.
                        # TODO: When is this actually used?
                        image_fully_read = True
                        break
                    
                    elif operation == 0x02:
                        # MARK THE START OF A KEYFRAME TRANSPARENCY REGION.
                        # Until a color index other than 0x00 (usually white) is read on this line,
                        # all pixels on this line will be marked transparent. 
                        # 
                        # If no transparency regions are present in this image, all 0x00 color indices are treated 
                        # as transparent. Otherwise, only the 0x00 color indices within transparency regions
                        # are considered transparent. Only intraframes (frames that are not keyframes) have been
                        # observed to have transparency regions, and these intraframes have them so the keyframe
                        # can extend outside the boundary of the intraframe and still be removed.
                        self.transparency_region.append([horizontal_pixel_offset, row_index])
                        reading_transparency_run = True
                        pass
                    
                    elif operation == 0x03:
                        # ADJUST THE PIXEL POSITION.
                        # This permits jumping to a different part of the same row without
                        # needing a run of pixels in between. But the actual data consumed
                        # seems to actually be higher this way, as you need the control byte
                        # first. 
                        #
                        # So to skip 10 pixels using this approach, you would encode 00 03 0a 00.
                        # But to "skip" 10 pixels by encoding them as blank (0xff), you would encode 0a ff.
                        # What gives? I'm not sure. 
                        x_change = struct.unpack.uint8(compressed_image_data)
                        horizontal_pixel_offset += x_change
                        y_change = struct.unpack.uint8(compressed_image_data) 
                        row_index += y_change

                    elif operation >= 0x04: 
                        # READ A RUN OF UNCOMPRESSED PIXELS.
                        color_index_to_repeat = compressed_image_data.read(operation)
                        vertical_pixel_offset = (row_index * self.width)
                        run_starting_offset = vertical_pixel_offset + horizontal_pixel_offset
                        pixels[run_starting_offset:run_starting_offset+len(color_index_to_repeat)] = color_index_to_repeat

                        horizontal_pixel_offset += len(color_index_to_repeat)
                        if compressed_image_data.tell() % 2 == 1:
                            compressed_image_data.read(1)

                else:
                    # READ A RUN OF LENGTH ENCODED PIXELS.
                    vertical_pixel_offset = (row_index * self.width)
                    run_starting_offset = vertical_pixel_offset + horizontal_pixel_offset
                    color_index_to_repeat = compressed_image_data.read(1)
                    repetition_count = operation

                    pixels[run_starting_offset:run_starting_offset+operation] = repetition_count * color_index_to_repeat
                    horizontal_pixel_offset += repetition_count
                    #if compressed_image_data.tell() % 2 == 1:
                    #    compressed_image_data.read(1)

                    if reading_transparency_run:
                        # MARK THE END OF THE TRANSPARENCY REGION.
                        # The "interior" of transparency regions is always encoded by a single run of
                        # pixels, usually 0x00 (white).
                        self.transparency_region[-1].append(operation)
                        reading_transparency_run = False

            row_index += 1
            if image_fully_read: 
                break

        self._pixels = bytes(pixels)

    ## \return The decompressed pixels that represent this image.
    ## The number of bytes is the same as the product of the width and the height.
    @property
    def pixels(self) -> bytes:
        if self._pixels is None and self._compressed_image_data_size > 0:
            self.decompress_bitmap()
        return self._pixels
