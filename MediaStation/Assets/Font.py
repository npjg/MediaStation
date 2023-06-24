
import os
from pathlib import Path

from asset_extraction_framework.Asset.Animation import Animation
from asset_extraction_framework.Asserts import assert_equal

from ..Primitives.Datum import Datum
from ..Primitives.Point import Point
from .Bitmap import Bitmap

## A single glyph (bitmap) in a font.
class FontGlyph(Bitmap):
    def __init__(self, stream, end):
        self.ascii_code = Datum(stream).d
        self.unk1 = Datum(stream).d
        self.unk2 = Datum(stream).d
        assert_equal(Datum(stream).d, 0x0024)
        dimensions = Datum(stream).d
        assert_equal(Datum(stream).d, 0x0001)
        self.unk3 = Datum(stream).d

        # READ THE FONT GLYPH BITMAP.
        image_length = end - stream.tell()
        super().__init__(stream, dimensions = dimensions, length = image_length)

## A font is a collection of glyphs.
## Fonts have a very similar structure as sprites, but fonts are of course
## not animations so they do not derive from the animation class.
class Font:
    def __init__(self, header):
        self.name = None
        self.glyphs = []

    ## Adds a glyph to the font collection.
    def append(self, stream, length):
        end = stream.tell() + length
        font_glyph = FontGlyph(stream, end)
        self.glyphs.append(font_glyph)

    ## Since the font is not an animation, each character in the font should
    ## always be exported separately.
    def export(self, root_directory_path, command_line_arguments):
        frame_export_directory_path = os.path.join(root_directory_path, self.name)
        Path(frame_export_directory_path).mkdir(parents = True, exist_ok = True) 

        for index, glyph in enumerate(self.glyphs):
            filename_without_extension = os.path.join(frame_export_directory_path, f'{index}')
            glyph.export(filename_without_extension, command_line_arguments)