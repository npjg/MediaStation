
from asset_extraction_framework.Asset.Animation import Animation
from asset_extraction_framework.Asserts import assert_equal

from ..Primitives.Datum import Datum
from ..Primitives.Point import Point
from .Bitmap import Bitmap, BitmapHeader

## An extended bitmap header for a single sprite frame. 
class SpriteFrameHeader(BitmapHeader):
    ## Reads a sprite header from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        super().__init__(stream)
        # The sprite header has two extra fields not in the basic bitmap header.
        # The index of this frame in the sprite animation (zero-based).
        self.index = Datum(stream).d
        self.bounding_box = Datum(stream).d

## A single frame in a sprite.
class SpriteFrame(Bitmap):
    ## Reads a sprite frame from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] size - The total size, in bytes, of this sprite frame.
    ##            This number of bytes will be read from the stream.
    def __init__(self, chunk):
        super().__init__(chunk, header_class = SpriteFrameHeader)
        self._left = 0
        self._top = 0

## A sprite is a special kind of animation:
## - It automatically runs when the context is shown (TODO: Is this always true?)
## - It has no audio.
class Sprite(Animation):
    ## Creates a sprite. All frames must be added manually. (TODO: Document why.)
    def __init__(self, header):
        super().__init__()
        self._width = header.bounding_box.dimensions.x
        self._height = header.bounding_box.dimensions.y
        self._left = header.bounding_box.left_top_point.x
        self._top = header.bounding_box.left_top_point.y

    ## Reads a sprite frame from a binary stream at its current position
    ## and adds it to the collection of frames in this sprite.
    ## \param[in] stream - A binary stream that supports the read method.
    ## \param[in] size - The total size, in bytes, of the sprite frame.
    ##            This number of bytes will be read from the stream.
    def append(self, chunk):
        sprite_frame = SpriteFrame(chunk)
        self.frames.append(sprite_frame)
        self.frames.sort(key = lambda x: x.header.index)
