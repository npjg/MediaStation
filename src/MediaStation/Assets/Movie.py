
from enum import IntEnum
import os

import numpy as np
from PIL import Image
from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.Asset.Animation import Animation

from asset_extraction_framework.Exceptions import BinaryParsingError
from .. import global_variables
from ..Primitives.Datum import Datum
from ..Primitives.Point import Point
from .Bitmap import Bitmap, BitmapHeader
from .Sound import Sound

# ATTEMPT TO IMPORT THE C-BASED DECOMPRESSION LIBRARY.
# We will fall back to the pure Python implementation if it doesn't work, but there is easily a 
# 10x slowdown with pure Python.
try:
    import MediaStationBitmapRle
    rle_c_loaded = True
except ImportError:
    # We don't need a warning here since it is already issued in the bitmap
    # decompression library.
    rle_c_loaded = False

## Metadata that occurs after each movie frame and most keyframes.
## The only instance where it does not have a keyframe is...
## For example:
##   -- BEGIN SUBFILE --
##     Frame 001 starts at 0 ms, ends at 150 ms.
##     Frame 002 (keyframe) starts at 150 ms, ends at 1500 ms.
##     Frame 003 starts at 150 ms, ends at 300 ms.
##   -- END SUBFILE --
##   -- BEGIN SUBFILE --
##    Frame 004 starts at 300 ms, ends at 450 ms.
##    Frame 002 starts at 450 ms, ends at 600 ms.
##    ...
## The first and second occurrences of Frame 002 have different image data:
##  - The first occurrence has the complete keyframe but has no footer.
##  - The second occurrence is usually completely transparent to show the key
##    frame as it is, but this has a footer.
## This is a pretty weird format, but it is what it is.
class MovieFrameFooter:
    ## Reads a movie frame header from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # TODO: Determine what this is.
        self.unk1 = Datum(stream).d # This seems to always be 0x01.
        self.unk2 = Datum(stream).d
        if global_variables.version.is_first_generation_engine or \
              ((global_variables.version.major_version <= 3) and (global_variables.version.minor_version <= 2)):
            # It is theoretically possible for movies to have a variable
            # framerate, but in reality all these are the same.
            self.start_in_milliseconds =  Datum(stream).d
            self.end_in_milliseconds = Datum(stream).d
            # inside bbox.
            self._left = Datum(stream).d
            self._top = Datum(stream).d
            # TODO: Identify these fields.
            self.unk3 = Datum(stream).d
            self.unk4 = Datum(stream).d
            # This index is zero-based.
            self.index = Datum(stream).d
        else:
            self.unk4 = Datum(stream).d
            # It is theoretically possible for movies to have a variable
            # framerate, but in reality all these are the same.
            self.start_in_milliseconds =  Datum(stream).d
            self.end_in_milliseconds = Datum(stream).d
            # inside bbox.
            self._left = Datum(stream).d
            self._top = Datum(stream).d
            # TODO: Identify these fields.
            self.unk5 = Datum(stream).d
            self.unk6 = Datum(stream).d
            self.unk7 = Datum(stream).d
            # This index is zero-based.
            self.index = Datum(stream).d
            self.unk8 = Datum(stream).d
            self.unk9 = Datum(stream).d

## An extended bitmap header for a single movie frame. 
class MovieFrameHeader(BitmapHeader):
    ## Reads a movie frame header from the binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # The movie frame header has two extra fields not in the basic bitmap header.
        super().__init__(stream)
        self.index = Datum(stream).d
        self.keyframe_end_in_milliseconds = Datum(stream).d

## A single bitmap frame in a movie.
class MovieFrame(Bitmap):
    def __init__(self, chunk):
        # READ THE IMAGE.
        super().__init__(chunk, header_class = MovieFrameHeader)
        # The footer must be added separately because it is not always present,
        # and the footer right after this frame might not actually correspond to
        # this frame.
        self.footer = None
        # These coordinates are relative to the whole screen, not just to this movie.
        self._left = 0
        self._top = 0
        self.full_width = None
        self.full_height = None

    def set_footer(self, footer: MovieFrameFooter):
        self.footer = footer
        self._left = self.footer._left
        self._top = self.footer._top

    def decompress_bitmap(self, full_width, full_height, keyframe = None):
        self.full_width = full_width
        self.full_height = full_height
        self._pixels = MediaStationBitmapRle.decompress(
            self._raw, self.width, self.height, full_width, full_height, self._left, self._top, keyframe)

    def export(self, root_directory_path: str, command_line_arguments):
        # TODO: This is a nasty hack to get the animation-framed dimensions right!
        if self.pixels is not None:
            old_width = self._width
            old_height = self._height
            self._width = self.full_width
            self._height = self.full_height
            super().export(root_directory_path, command_line_arguments)
            self._width = old_width
            self._height = old_height

## A single animation.
##  - A series of bitmaps.
##  - Optional sound.
##  - Zero or more "stills".
## A movie consists of a bunch of chunks.
class Movie(Animation):
    class SectionType(IntEnum):
        ROOT = 0x06a8
        FRAME = 0x06a9
        FOOTER = 0x06aa

    ## Initialize a movie. This does not do any reading,
    ## as there are multiple parts to the movie that
    ## must be read separately.
    def __init__(self, header):
        super().__init__()
        self.name = header.name
        self._sound_encoding = header.sound_encoding
        self._alpha_color = 0x00
        self._width = header.bounding_box.dimensions.x
        self._height = header.bounding_box.dimensions.y
        self._left = header.bounding_box.left_top_point.x
        self._top = header.bounding_box.left_top_point.y

    ## Read a still from a binary stream at its current position.
    ## TODO: Are all the frames followed by a footer chunk?
    def add_still(self, chunk):
        section_type = Datum(chunk)
        if section_type.d == Movie.SectionType.FRAME:
            frame = MovieFrame(chunk)
            self.frames.append(frame)

        elif section_type.d == Movie.SectionType.FOOTER:
            footer = MovieFrameFooter(chunk)
            for frame in self.frames:
                if frame.header.index == footer.index:
                    frame.set_footer(footer)

        else:
            raise BinaryParsingError(f'Unknown header type in movie still area: 0x{section_type.d:02x}', chunk.stream)

    ## Reads the data in a subfile from the binary stream at its current position.
    ## The subfile's metadata must have already been read.
    ## \param[in] subfile - The subfile to read. The binary stream must generally
    ## be at the start of the subfile.
    def add_subfile(self, subfile, chunk):
        header_chunk_integer = chunk.chunk_integer + 0
        video_chunk_integer = chunk.chunk_integer + 1
        audio_chunk_integer = chunk.chunk_integer + 2

        # READ THE METADATA FOR THIS MOVIE.
        section_type = Datum(chunk).d
        assert_equal(section_type, Movie.SectionType.ROOT, "movie root signature")
        chunk_count = Datum(chunk).d
        start_pointer = Datum(chunk).d
        chunk_sizes = []
        for _ in range(chunk_count):
            chunk_size = Datum(chunk).d
            chunk_sizes.append(chunk_size)

        # READ THE MOVIE CHUNKS.
        for index in range(chunk_count):
            # READ THE NEXT CHUNK.
            chunk = subfile.get_next_chunk()
            frames = []
            footers = []

            # READ ALL THE IMAGES (FRAMES).
            # Video always comes first.
            is_video_chunk = (chunk.chunk_integer == video_chunk_integer)
            movie_frame: MovieFrame = None
            while is_video_chunk:
                section_type = Datum(chunk).d
                if (Movie.SectionType.FRAME == section_type):
                    # READ THE MOVIE FRAME.
                    movie_frame = MovieFrame(chunk)
                    frames.append(movie_frame)

                elif (Movie.SectionType.FOOTER == section_type):
                    # READ THE MOVIE FRAME FOOTER.
                    footer = MovieFrameFooter(chunk)
                    footers.append(footer)

                else:
                    raise TypeError(f'Unknown movie chunk tag: 0x{section_type:04x}')

                # READ THE NEXT CHUNK.
                chunk = subfile.get_next_chunk()
                is_video_chunk = (chunk.chunk_integer == video_chunk_integer)

            # READ THE AUDIO.
            is_audio_chunk = (subfile.current_chunk.chunk_integer == audio_chunk_integer)
            if is_audio_chunk:
                audio = Sound(self._sound_encoding)
                audio.read_chunk(chunk)
                self.sounds.append(audio)
                chunk = subfile.get_next_chunk()

            # READ THE FOOTER FOR THIS SUBFILE.
            # Every frameset must end in a 4-byte header.
            # TODO: Figure out what this is.
            is_header_chunk = (chunk.chunk_integer == header_chunk_integer)
            if is_header_chunk:
                assert_equal(chunk.length, 0x04, "frameset delimiter size")
                chunk.read(chunk.length)
            else:
                raise BinaryParsingError(f'Unknown delimiter at end of movie frameset: {subfile.current_chunk.fourcc}', chunk.stream)
            
            # SET THE REQUIRED FOOTERS.
            # Most keyframes don't have any different metadata from regular frames (aside from duration).
            # Notably, they have footers just like normal frames.
            for footer in footers:
                for frame in frames:
                    if (frame.header.index == footer.index) and (frame.footer is None):
                        frame.set_footer(footer)

            self.frames.extend(frames)

    # Currently doesn't handle keyframes that end in the middle of another frame,
    # but that seems an unlikely occurrence.
    # The animation framing MUST be applied or there will be an error when applying the keyframing.
    def _apply_keyframes(self):
        timestamp = -1
        current_keyframe: MovieFrame = None
        # TODO: Need to determine why some movies aren't exported.
        for index, frame in enumerate(self.frames):
            global_variables.application.logger.debug(f'[{self.name}] ({index}) Keyframing frame {frame.header.index} (timestamp: {timestamp}) (start: {frame.footer.start_in_milliseconds if frame.footer else None}) (end: {frame.footer.end_in_milliseconds if frame.footer else None}) (keyframe_end: {frame.header.keyframe_end_in_milliseconds}) (current_keyframe: {current_keyframe.header.index if current_keyframe else None})')

            # CORRECT THE COORDINATES OF THIS FRAME.
            # TODO: Document why this is necessary.
            if frame.footer is None:
                for frame_with_dimensions in self.frames:
                    if (frame.header.index == frame_with_dimensions.header.index):
                        frame._left = frame_with_dimensions._left
                        frame._top = frame_with_dimensions._top

            # CHECK IF WE SHOULD REGISTER THE NEXT KEYFRAME.
            if frame.header.keyframe_end_in_milliseconds > timestamp:
                timestamp = frame.header.keyframe_end_in_milliseconds
                if current_keyframe is None or current_keyframe.header.index != frame.header.index:
                    # REGISTER THE NEXT KEYFRAME.
                    # The keyframe is not intended to be included in the export.
                    # Though maybe we could include them as some sort of
                    # "K1.bmp" filename to help with debugging.
                    global_variables.application.logger.debug(f'[{self.name}] Registering next keyframe {frame.header.index}')
                    current_keyframe = frame
                    current_keyframe.decompress_bitmap(self._width, self._height)
                    current_keyframe._include_in_export = False
                    continue

            frame.decompress_bitmap(self._width, self._height, current_keyframe.pixels)

    def export(self, root_directory_path, command_line_arguments):
        # TODO: Should the stills be exported like everything else? They look like they might be regular frames.
        # TODO: Provide an option to check for a request to not apply keyframes. 
        self._apply_keyframes()
        super().export(root_directory_path, command_line_arguments)
