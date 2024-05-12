
import os
from pathlib import Path

from asset_extraction_framework.Asserts import assert_equal

from ..Primitives.Datum import Datum
from .Bitmap import Bitmap, BitmapHeader

## This is not an animation or a sprite but just a collection of static bitmaps.
## It is a fairly rare asset type, having only been observed in:
##  - Hercules, 1531.CXT. Seems to be some sort of changeable background.
##    This is denoted in the PROFILE._ST by a strange line:
##    "# image_7d12g_Background 15000 15001 15002 15003 15004 15005 15006 15007 15008 15009 15010 15011 15012 15013"
##    Indeed, there are 14 images in this set.

## Each bitmap is declared in the asset header.
class BitmapSetBitmapDeclaration:
    def __init__(self, stream):
        self.index = Datum(stream).d
        # This is the ID as reported in PROFILE.ST.
        # Using the example above, it's something like 15000, 15001,
        # and so forth. Should increase along with the indices
        self.id = Datum(stream).d
        # This includes the space requried for the header.
        self.chunk_length_in_bytes = Datum(stream).d

## The bitmap header for one of the bitmaps in the bitmap set.
class BitmapSetBitmapHeader(BitmapHeader):
    def __init__(self, stream):
        # Specifies the position of the bitmap in the bitmap set.
        self.index = Datum(stream).d
        super().__init__(stream)

class BitmapSet:
    def __init__(self, header):
        self._chunk_count = header.bitmap_count
        self.bitmaps = {}

    def apply_palette(self, palette):
        for _, bitmap in enumerate(self.bitmaps.values()):
            bitmap._palette = palette

    def read_subfile(self, subfile, chunk):
        asset_id = chunk.fourcc
        self.read_chunk(chunk)
        # TODO: I think this is dead code becuase in Hercules
        # there is just one chunk per subfile (unlike sounds).
        # However, I want to be sure before removing it.
        while not subfile.at_end:
            chunk = subfile.get_next_chunk()
            assert_equal(chunk.fourcc, asset_id, "bitmap set chunk label")
            self.read_chunk(chunk)

    def read_chunk(self, chunk):
        bitmap = Bitmap(chunk, header_class = BitmapSetBitmapHeader)

        # VERIFY BITMAP DATA WILL NOT BE LOST.
        existing_bitmap_with_same_index = self.bitmaps.get(bitmap.header.index) 
        if existing_bitmap_with_same_index is not None:
             # Interestingly, in Hercules the same images that occur in the first subfile
            # also seem to occur in later subfiles (with the same index). To make sure
            # no data is being lost, we will just ensure that the bitmap being replaced
            # has the exact same pixel data as the bitmap replacing it.
            assert bitmap.pixels == existing_bitmap_with_same_index.pixels
        self.bitmaps.update({bitmap.header.index: bitmap})

    def export(self, root_directory_path: str, command_line_arguments):
        # CREATE A SUBDIRECTORY.
        frame_export_directory_path = os.path.join(root_directory_path, self.name)
        Path(frame_export_directory_path).mkdir(parents = True, exist_ok = True)

        # EXPORT THE BITMAPS INTO THAT DIRECTORY.
        for _, bitmap in enumerate(self.bitmaps.values()):
            export_filepath = os.path.join(frame_export_directory_path, f'{bitmap.header.index}')
            bitmap.export(export_filepath, command_line_arguments)