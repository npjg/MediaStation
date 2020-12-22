#!/usr/bin/python3

import argparse
import logging

from enum import IntEnum
import struct
import io
from pathlib import Path
import os
import subprocess
import mmap
import pprint

import traceback

import PIL.Image as PILImage

class RecordType(IntEnum):
    CXT      = 0x0006,
    FILE_1   = 0x0008,
    FILE_3   = 0x0029,
    RIFF     = 0x0028,
    CURSOR   = 0x0015,
    RES_NAME = 0x0bba,
    RES_ID   = 0x0bbb,

class BootRecord(IntEnum):
    FILES_1  = 0x0002,
    FILES_2  = 0x0007,
    FILES_3  = 0x000a,
    RIFF     = 0x000b,
    CURSOR   = 0x000c,

class ChunkType(IntEnum):
    HEADER         = 0x000d,
    IMAGE          = 0x0018,
    MOVIE_ROOT     = 0x06a8,
    MOVIE_FRAME    = 0x06a9,
    MOVIE_HEADER   = 0x06aa,

class HeaderType(IntEnum):
    ROOT    = 0x000e,
    PALETTE = 0x05aa,
    UNK_D   = 0x0010,
    ASSET   = 0x0011,
    LINK    = 0x0013,
    FUNC    = 0x0031,

class AssetType(IntEnum):
    SCR  = 0x0001,
    STG  = 0x0002,
    PTH  = 0x0004,
    SND  = 0x0005,
    TMR  = 0x0006,
    IMG  = 0x0007,
    HSP  = 0x000b,
    SPR  = 0x000e,
    MOV  = 0x0016,
    PAL  = 0x0017,
    TXT  = 0x001a,
    FON  = 0x001b,
    CAM  = 0x001c,
    CVS  = 0x001e,
    FUN  = 0x0069,

class DatumType(IntEnum):
    UINT8   = 0x0002,
    UINT16  = 0x0003,
    UINT32_1  = 0x0004,
    UINT32_2  = 0x0007,
    UINT16_2 = 0x0013,
    UINT16_3  = 0x0006,
    SINT16  = 0x0010,
    FLOAT64_1  = 0x0011,
    FLOAT64_2  = 0x0009,
    STRING  = 0x0012,
    FILE    = 0x000a,
    POINT   = 0x000f,
    POINT_2 = 0x000e,
    PALETTE = 0x05aa,
    REF     = 0x001b,
    BBOX    = 0x000d,
    POLY    = 0x001d,

def chunk_int(chunk):
    try: return int(chunk['code'][1:], 16)
    except: return None

def read_chunk(stream):
    if stream.tell() % 2 == 1:
        stream.read(1)

    chunk = {
        "start": stream.tell(),
        "code": stream.read(4).decode("utf-8"),
        "size": struct.unpack("<L", stream.read(4))[0]
    }

    logging.debug("(@0x{:012x}) Read chunk {} (0x{:04x} bytes)".format(stream.tell(), chunk["code"], chunk["size"]))
    return chunk

def read_riff(stream):
    outer = read_chunk(stream)
    value_assert(outer["code"], "RIFF", "signature")

    value_assert(stream, b'IMTS', "signature")
    value_assert(stream, b'rate', "signature")
    rate = stream.read(struct.unpack("<L", stream.read(4))[0])

    inner = read_chunk(stream)
    value_assert(inner["code"], "LIST", "signature")

    value_assert(stream, b'data', "signature")
    return inner["size"] + (stream.tell() - outer["start"]) - 8

def value_assert(stream, target, type="value", warn=False):
    ax = stream
    try:
        ax = stream.read(len(target))
    except AttributeError:
        pass

    msg = "Expected {} {}{}, received {}{}".format(
        type, target, " (0x{:0>4x})".format(target) if isinstance(target, int) else "",
        ax, " (0x{:0>4x})".format(ax) if isinstance(ax, int) else "",
    )
    if warn and ax != target:
        logging.warning(msg)
    else:
        assert ax == target, msg


############### INTERNAL DATA REPRESENTATIONS ############################

class Object:
    def __format__(self, spec):
        return self.__repr__()

class Datum(Object):
    def __init__(self, stream, parent=None, peek=False):
        self.start = stream.tell()
        self.d = None
        self.t = struct.unpack("<H", stream.read(2))[0]

        if self.t == DatumType.UINT8:
            self.d = int.from_bytes(stream.read(1), byteorder='little')
        elif self.t == DatumType.UINT16 or self.t == DatumType.UINT16_2 or self.t == DatumType.UINT16_3:
            self.d = struct.unpack("<H", stream.read(2))[0]
        elif self.t == DatumType.SINT16:
            self.d = struct.unpack("<H", stream.read(2))[0]
        elif self.t == DatumType.UINT32_1 or self.t == DatumType.UINT32_2:
            self.d = struct.unpack("<L", stream.read(4))[0]
        elif self.t == DatumType.FLOAT64_1 or self.t == DatumType.FLOAT64_2:
            self.d = struct.unpack("<d", stream.read(8))[0]
        elif self.t == DatumType.STRING or self.t == DatumType.FILE:
            size = Datum(stream)
            self.d = stream.read(size.d).decode("utf-8")
        elif self.t == DatumType.BBOX:
            self.d = Bbox(stream)
        elif self.t == DatumType.POINT or self.t == DatumType.POINT_2:
            self.d = Point(stream)
        elif self.t == DatumType.REF:
            self.d = Ref(stream, parent.type if parent else None)
        else:
            raise TypeError(
                "(@ 0x{:0>12x}) Unknown datum type 0x{:0>4x}".format(stream.tell(), self.t)
            )

        if peek: stream.seek(self.start)

    def __repr__(self):
        data = ""
        base = "<Datum: 0x{:0>4x}; type: 0x{:0>4x}, ".format(
            self.start, self.t
        )
        
        try:
            if len(self.d) > 0x12 and not isinstance(self.d, str):
                data = "<length: 0x{:0>6x}>>".format(len(self.d))
            else:
                data = "data: {}>".format(self.d)
        except:
            data = "data: {}{}{}>".format(
                "0x" if isinstance(self.d, int) else "",
                "{:0>6x}".format(self.d) if isinstance(self.d, int) else "{:0>6.2f}".format(self.d),
                " ({:0>4d})".format(self.d) if isinstance(self.d, int) else ""
            )
            
        return base + data

class Ref(Object):
    def __init__(self, stream, type):
        self.refs = []

        if not type:
            logging.warning("cxt.Ref(): No parent type specified, assuming simple type")
            self.append(stream)
        elif type.d in (AssetType.SPR, AssetType.IMG, AssetType.SND, AssetType.FON):
            self.append(stream)
        elif type.d == AssetType.MOV:
            self.append(stream)
            stream.read(2)

            self.append(stream)
            stream.read(2)

            self.append(stream)
        else:
            raise ValueError("cxt.Ref(): Reference for unexpected asset type: {} (0x{:04x})".format(type.d, type.d))

    def append(self, stream):
        self.refs.append(
            (stream.read(4).decode("utf-8"), Datum(stream))
        )

    def id(self, string=False):
        return [int(ref[0][1:], 16) if string else ref[0] for ref in self.refs]

    def __repr__(self):
        return "<Ref: {})>".format([(s, i) for s, i in zip(self.id(), self.id(string=True))])

class Point(Object):
    def __init__(self, m, **kwargs):
        if m:
            value_assert(m, b'\x10\x00', "chunk")
            self.x = struct.unpack("<H", m.read(2))[0]

            value_assert(m, b'\x10\x00', "chunk")
            self.y = struct.unpack("<H", m.read(2))[0]
        else:
            self.x = kwargs.get("x")
            self.y = kwargs.get("y")

    def __repr__(self):
        return "<Point: x: {:03d}, y: {:03d}>".format(self.x, self.y)

class Bbox(Object):
    def __init__(self, m):
        value_assert(m, b'\x0e\x00', "chunk")
        self.point = Point(m)

        value_assert(m, b'\x0f\x00', "chunk")
        self.dims = Point(m)

    def __repr__(self):
        return "<Bbox: {}, {}, {}, {}>".format(
            self.point.x, self.point.x + self.dims.x,
            self.point.y, self.point.y + self.dims.y
        )

class Polygon(Object):
    def __init__(self, stream):
        size = Datum(stream)

        self.points = []
        for _ in range(size):
            stream.read(2)
            self.points.append(Point(stream))

    def __repr__(self):
        return "<Polygon: points: {}>".format(len(self.points))

class Array(Object):
    def __init__(self, stream, parent=None, bytes=None, datums=None, stop=None):
        self.datums = []
        start = stream.tell()

        if bytes == 0 and not datums and not stop:
            return
        if not datums and not bytes and not stop:
            raise AttributeError("Creating an array requires providing a bytes size or a stop parameter.")

        while True:
            d = Datum(stream, parent=parent if parent else self)
            if stop and d.t == stop[0] and d.d == stop[1]:
                break

            self.datums.append(d)
            if bytes and stream.tell() >= bytes + start:
                break
            if datums and len(self.datums) == datums:
                break

        logging.debug("Read 0x{:04x} array bytes".format(stream.tell() - start))

    def log(self):
        logging.debug(self)
        for datum in self.datums:
            logging.debug(" -> {}".format(datum))

    def export(self, directory, filename, fmt="bytes.txt", **kwargs):
        filename = os.path.join(directory, filename)

        if filename[-4:] != ".{}".format(fmt):
            filename += (".{}".format(fmt))

        with open(filename, 'w') as f:
            for datum in self.datums:
                print(datum, file=f)

    def __repr__(self):
        return "<Array: size: {:0>4d}>".format(len(self.datums))

class AssetHeader(Object):
    def __init__(self, stream, size, string, stop=None):
        end = stream.tell() + size
        self.data = Array(stream, datums=4)

        # TODO: Handle children more generally.
        self.child = None
        if string: self.data.datums.pop(-1) # pop the string header to keep indexing consistent
        self.name = Datum(stream) if string else None

        if self.data.datums[1].d == AssetType.PAL:
            value_assert(Datum(stream).d, DatumType.PALETTE, "palette signature")
            self.child = stream.read(0x300)
            logging.debug("Read 0x{:04x} palette bytes".format(0x300))
            value_assert(Datum(stream).d, 0x00, "end-of-chunk flag")
        elif self.data.datums[1].d == AssetType.STG:
            logging.debug("Reading stage asset...")

            self.data.datums += Array(stream, parent=self, stop=(DatumType.UINT16, 0x0000)).datums

            value_assert(Datum(stream).d, HeaderType.LINK, "link signature")
            value_assert(Datum(stream).d, self.id.d, "asset id")

            self.child = []
            if self.data.datums[8].d != 0x0000: # TODO: What is this, exactly?
                value_assert(Datum(stream).d, HeaderType.ASSET, "stage asset chunk")
                while stream.tell() < end:
                    header = AssetHeader(
                        stream, size=end-stream.tell(), string=string, stop=(DatumType.UINT16, HeaderType.ASSET)
                    )

                    self.child.append(header)
                    logging.debug("Added asset header to stage: -> {}".format(header))
        elif self.data.datums[1].d == AssetType.HSP:
            self.data.datums += Array(stream, parent=self, stop=(DatumType.UINT16, 0x0000)).datums

            if stream.tell() < end and Datum(stream).d == DatumType.POLY:
                logging.debug("Searching for polygon points...")
                value_assert(Datum(stream).d, DatumType.POLY, "polygon header")
                self.child = Polygon(stream)
                value_assert(Datum(stream).d, 0x0000, "end of polygon")
        elif self.data.datums[1].d == AssetType.FUN: # Put the bytecode in an array for now
            self.child = Array(stream, parent=self, bytes=end-stream.tell())
        else:
            self.data.datums += Array(stream, parent=self, bytes=end-stream.tell(), stop=stop).datums

        if size and not stop and stream.tell() < end:
            logging.warning("{} bytes left in asset header >>> {}".format(end-stream.tell(), self))
            stream.read(end - stream.tell())

    @property
    def filenum(self):
        return self.data.datums[0]

    @property
    def type(self):
        return self.data.datums[1]

    @property
    def id(self):
        return self.data.datums[2]

    @property
    def ref(self):
        # TODO: Enumerate all types that have associated data chunks
        for datum in self.data.datums:
            if datum.t == DatumType.REF:
                return datum

    def __repr__(self):
        return "<AssetHeader: parent: {}, type: 0x{:0>4x}, id: 0x{:0>4x} ({:0>4d}){}{}>".format(
            self.filenum.d, self.type.d, self.id.d, self.id.d,
            " {}".format(self.ref.d) if self.ref else "",
            ", name: {}".format(self.name.d) if self.name else ""
        )

class AssetLink(Object):
    def __init__(self, stream, size):
        # TODO: Determine the lengths of these asset links.
        self.type = Datum(stream)
        self.data = Array(stream, bytes=size-0x04)

    @property
    def ids(self):
        # For now, we just skip the even indices, as these are delimiters.
        return self.data.datums[::2]


############### EXTERNAL DATA REPRESENTATIONS ############################

class ImageHeader(Object):
    def __init__(self, stream):
        self.start = stream.tell()

        value_assert(Datum(stream).d, ChunkType.IMAGE, "image signature") # Is this actually a byte count?
        self.dims = Datum(stream)
        self.compressed = Datum(stream)
        self.unk1 = Datum(stream)

    def __repr__(self):
        return "<ImageHeader: 0x{:06x}; dims: {}, compressed: {}, unk1: 0x{:04x} ({:04d})".format(
            self.start, self.dims.d, self.compressed.d, self.unk1.d, self.unk1.d
        )

class Image(Object):
    def __init__(self, stream, size, dims=None):
        end = stream.tell() + size

        self.header = None
        self.dims = dims
        if not dims:
            self.header = ImageHeader(stream)

        self.raw = io.BytesIO(stream.read(end-stream.tell()))
        if not dims:
            value_assert(self.raw, b'\x00\x00', "image row header")

        logging.debug("Read 0x{:04x} raw image bytes".format(size))
        self.offset = 0

    @property
    def image(self):
        self.raw.seek(0)
        if not self.compressed:
            return self.raw.read()

        done = False
        image = bytearray((self.width*self.height) * b'\x00')
        for h in range(self.height):
            self.offset = 0
            while True:
                code = int.from_bytes(self.raw.read(1), byteorder='little')

                if code == 0x00: # control mode
                    op = int.from_bytes(self.raw.read(1), byteorder='little')
                    if op == 0x00: # end of line
                        # logging.debug("Image.image: Reached end of line")
                        break

                    if op == 0x01: # end of image
                        # logging.debug("Image.image: Reached end of image")
                        done = True
                        break

                    if op == 0x03: # offset for RLE
                        delta = struct.unpack("<H", self.raw.read(2))[0]
                        self.offset += delta
                        # logging.debug("Image.image: Set new offset {} (delta {})".format(self.offset, delta))
                    else: # uncompressed data of given length
                        # logging.debug("Image.image: Found {} uncompressed bytes at 0x{:04x}".format(op, self.raw.tell()))
                        pix = self.raw.read(op)

                        loc = (h * self.width) + self.offset
                        if loc + len(pix) > self.width * self.height:
                            logging.warning("Image(): Exceeded bounds of array by 0x{:04x}".format((loc + len(pix)) - self.width * self.height))

                        image[loc:loc+len(pix)] = pix

                        if self.raw.tell() % 2 == 1:
                            self.raw.read(1)

                        self.offset += len(pix)
                else: # RLE data
                    # logging.debug("Image.image: Found {} RLE pixels".format(code))
                    loc = (h * self.width) + self.offset

                    pix = self.raw.read(1)
                    image[loc:loc+code] = code * pix
                    if loc + code > self.width * self.height:
                        logging.warning("Image(): Exceeded bounds of array by 0x{:04x}".format((loc + code) - self.width * self.height))

                    self.offset += code

            if done: break

        value_assert(
            len(image), self.width*self.height,
            "image length ({} x {})".format(self.width, self.height), warn=True
        )
        return bytes(image)

    def export(self, directory, filename, fmt="png", **kwargs):
        if self.width == 0 and self.height == 0:
            logging.warning("Found image with length and width 0, skipping export")
            return

        filename = os.path.join(directory, filename)
        if kwargs.get("with_header") and self.header:
            with open(os.path.join(directory, "header.txt"), 'w') as header:
                print(repr(self.header), file=header)

        if filename[-4:] != ".{}".format(fmt):
            filename += (".{}".format(fmt))

        # TODO: Find out where the palette information is stored.
        image = PILImage.frombytes("P", (self.width, self.height), self.image)
        if 'palette' in kwargs and kwargs['palette']:
            image.putpalette(kwargs['palette'])

        image.save(filename, fmt)

    @property
    def compressed(self):
        return bool((self.header and self.header.compressed.d) or self.dims)

    @property
    def width(self):
        return self.dims.d.x if self.dims else self.header.dims.d.x

    @property
    def height(self):
        return self.dims.d.y if self.dims else self.header.dims.d.y

    def __repr__(self):
        return "<Image: size: {} x {}>".format(self.width, self.height)

class MovieHeaderOuter(Object):
    def __init__(self, stream):
        self.start = stream.tell()

        value_assert(Datum(stream).d, 0x0001)
        value_assert(Datum(stream).d, 0x0000)
        self.unks = []

        self.unks.append(Datum(stream))
        self.duration = (Datum(stream), Datum(stream)) # milliseconds
        self.dims = Point(None, x=Datum(stream).d, y=Datum(stream).d) # inside bbox

        for _ in range(3):
            self.unks.append(Datum(stream))

        self.index = Datum(stream)

        for _ in range(2):
            self.unks.append(Datum(stream))

    def __repr__(self):
        return "<MovieHeaderOuter: 0x{:06x}; index: {:03d}, duration: {}, dims: {}\n ---> unks: {}".format(
            self.start, self.index.d, ["{:06d}".format(d.d) for d in self.duration], self.dims, self.unks
        )

class MovieHeaderInner(Object):
    def __init__(self, stream):
        self.start = stream.tell()

        value_assert(Datum(stream).d, 0x0028)
        self.dims = Datum(stream)
        value_assert(Datum(stream).d, 0x0001)
        unk1 = Datum(stream)
        self.index = Datum(stream)
        self.end = Datum(stream)

    def __repr__(self):
        return "<MovieHeaderInner: 0x{:06x}; index: {:03d}, end: {:06d}, dims: {}".format(
            self.start, self.index.d, self.end.d, self.dims.d
        )

class MovieFrame(Object):
    def __init__(self, stream, size):
        end = stream.tell() + size
        self.header = MovieHeaderInner(stream)
        self.image = Image(stream, size=end-stream.tell(), dims=self.header.dims)

class Movie(Object):
    def __init__(self, stream, header, chunk, stills=None):
        self.stills = stills
        self.chunks = []

        end = stream.tell() + chunk['size']
        codes = {
            "header": chunk_int(chunk),
            "video" : chunk_int(chunk) + 1,
            "audio" : chunk_int(chunk) + 2,
        }

        value_assert(Datum(stream).d, ChunkType.MOVIE_ROOT, "movie root signature")
        self.chunk_count = Datum(stream)
        self.start = Datum(stream)
        self.sizes = []
        for _ in range(self.chunk_count.d):
            self.sizes.append(Datum(stream))

        assert stream.tell() == end
        logging.debug(" *** Movie(): Expecting {} movie framesets ***".format(self.chunk_count.d))

        for i in range(self.chunk_count.d):
            chunk = read_chunk(stream)
            frames = []
            headers = []

            # Video comes first
            while chunk_int(chunk) == codes["video"]:
                type = Datum(stream)

                if type.d == ChunkType.MOVIE_FRAME:
                    logging.debug("Movie(): Reading movie frame of size 0x{:04x}".format(chunk['size']))
                    frames.append(MovieFrame(stream, size=chunk['size']-0x04))
                elif type.d == ChunkType.MOVIE_HEADER:
                    logging.debug("Movie(): Reading movie frame header of size 0x{:04x}".format(chunk['size']-0x04))
                    headers.append(MovieHeaderOuter(stream))

                chunk = read_chunk(stream)

            self.chunks.append({
                "frames": list(zip(headers, frames)),
                "audio": stream.read(chunk['size']) if chunk_int(chunk) == codes["audio"] else None
            })

            # Audio for the frameset comes last
            if chunk_int(chunk) == codes["audio"]:
                logging.debug("Movie(): Registered audio chunk for frameset")
                chunk = read_chunk(stream)

            # Every frameset must end in a 4-byte header
            if chunk_int(chunk) == codes["header"]:
                value_assert(chunk['size'], 0x04, "frameset delimiter size")
                stream.read(chunk['size'])
                logging.debug("Movie(): Read movie frameset delimiter")
            else:
                raise ValueError("Got unexpected delimiter at end of movie frameset: {}".format(chunk['code']))

            logging.debug(" ~~ Movie(): Finished frameset {} of {} ~~".format(i+1, self.chunk_count.d))

        logging.debug("Movie(): Finished reading movie: 0x{:012x}".format(stream.tell()))

    def export(self, directory, filename, fmt=("png", "wav"), **kwargs):
        if self.stills:
            for i, still in enumerate(zip(self.stills[0], self.stills[1])):
                still[0].image.export(directory, "still-{}".format(i), fmt=fmt[0], **kwargs)
                with open(os.path.join(directory, "still-{}.txt".format(i)), 'w') as still_header:
                    for datum in still[1].datums:
                        print(repr(datum), file=still_header)

        frame_headers = open(os.path.join(directory, "frame_headers.txt"), 'w')
        image_headers = open(os.path.join(directory, "image_headers.txt"), 'w')

        sound = Sound()

        for i, chunk in enumerate(self.chunks):
            for j, frame in enumerate(chunk["frames"]):
                # Handle the frame headers first
                print(" --- {}-{} ---".format(i, j), file=frame_headers)
                print(repr(frame[0]), file=frame_headers)

                # Now handle the actual frames
                print(" --- {}-{} ---".format(i, j), file=image_headers)
                print(repr(frame[1].header), file=image_headers)

                if frame[1].image:
                    frame[1].image.export(directory, "{}-{}".format(i, j), fmt=fmt[0], **kwargs)

            if chunk["audio"]: sound.append(chunk["audio"])

        sound.export(directory, "sound", fmt=fmt[1], **kwargs)

        frame_headers.close()
        image_headers.close()

    def __repr__(self):
        return "<Movie: chunks: {}>".format(len(self.chunks))

class SpriteHeader(Object):
    def __init__(self, stream):
        self.start = stream.tell()

        value_assert(Datum(stream).d, 0x0024) # Is this a size?
        self.dims = Datum(stream)
        value_assert(Datum(stream).d, 0x0001)
        self.unk1 = Datum(stream)
        self.index = Datum(stream)
        self.bbox = Datum(stream)

    def __repr__(self):
        return "<SpriteHeader: 0x{:06x}; index: {}, dims: {}, bbox: {}, unk: 0x{:04x}>".format(
            self.start, self.index.d, self.dims.d, self.bbox.d, self.unk1.d
        )

class Sprite(Object):
    def __init__(self):
        self.frames = []

    def append(self, stream, size):
        end = stream.tell() + size

        header = SpriteHeader(stream)
        self.frames.append({
            "header": header,
            "image": Image(stream, dims=header.dims, size=end-stream.tell())
        })

    def export(self, directory, filename, fmt="png", **kwargs):
        with open(os.path.join(directory, "headers.txt"), 'w') as headers:
            for i, frame in enumerate(self.frames):
                print(" --- {} --- ".format(i), file=headers)
                print(repr(frame["header"]), file=headers)

                if frame["image"].header:
                    print ("  |-- Image header --|  ", file=headers)
                    print(repr(frame["image"].header), file=headers)

                frame["image"].export(directory, str(i), fmt=fmt, **kwargs)

class FontHeader(Object):
    def __init__(self, stream):
        self.start = stream.tell()

        self.asc = Datum(stream) 
        self.unk1 = Datum(stream)
        self.unk2 = Datum(stream)
        value_assert(Datum(stream).d, 0x0024)
        self.dims = Datum(stream)
        value_assert(Datum(stream).d, 0x0001)
        self.unk3 = Datum(stream)

    def __repr__(self):
        return "<FontHeader: 0x{:06x}; ascii: 0x{:04x}, dims: {}, unk1: 0x{:04x}, unk2: 0x{:04x}, unk3: 0x{:04x}>".format(
            self.start, self.asc.d, self.dims.d, self.unk1.d, self.unk2.d, self.unk3.d
        )

class Font(Object):
    def __init__(self):
        self.glyphs = []

    def append(self, stream, size):
        end = stream.tell() + size

        header = FontHeader(stream)
        self.glyphs.append({
            "header": header,
            "glyph": Image(stream, dims=header.dims, size=end-stream.tell())
        })

    def export(self, directory, filename, fmt="png", **kwargs):
        with open(os.path.join(directory, "headers.txt"), 'w') as headers:
            for i, glyph in enumerate(self.glyphs):
                print(" --- {} ---".format(i), file=headers)
                print(repr(glyph["header"]), file=headers)

                if glyph["glyph"].header:
                    print ("  |-- Image header --|  ", file=headers)
                    print(repr(glyph["glyph"].header), file=headers)

                glyph["glyph"].export(directory, str(i), fmt=fmt, **kwargs)

class Sound(Object):
    def __init__(self, stream=None, header=None, chunk=None):
        self.chunks = []

        # If we provide these arguments, we want to read a while RIFF;
        # otherwise, this is for movie sound that we will add separately.
        if not stream or not header or not chunk:
            return

        # TODO: Determine what adds more information here.
        chunks = header.data.datums[9].d
        if chunks == header.id.d:
            chunks = header.data.datums[11].d
        logging.debug(" *** Sound(): Expecting {} sound chunks ***".format(chunks))

        asset_id = chunk["code"]
        self.append(stream, chunk["size"])
        for i in range(1, chunks):
            chunk = read_chunk(stream)
            value_assert(chunk["code"], asset_id, "sound chunk label")
            self.append(stream, chunk["size"])
            logging.debug(" ~~ Sound(): Finished chunk {} of {} ~~".format(i+1, chunks))

    def append(self, stream, size=0):
        if isinstance(stream, bytes):
            self.chunks.append(stream)
        else:
            logging.debug("Sound(): Reading sound chunk of size 0x{:04x}".format(size))
            self.chunks.append(stream.read(size))

    def export(self, directory, filename, fmt="wav", **kwargs):
        filename = os.path.join(directory, filename)

        with subprocess.Popen(
                ['ffmpeg', '-y', '-f', 's16le', '-ar', '11.025k', '-ac', '2', '-i', 'pipe:', filename+".{}".format(fmt)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE
        ) as process:
            for chunk in self.chunks:
                process.stdin.write(chunk)

            process.communicate()

        with open(os.path.join(directory, str(len(self.chunks))), 'w') as f:
            f.write(str(len(self.chunks)))


############### CONTEXT PARSER (*.CXT)  ##################################

class Context(Object):
    def __init__(self, stream, string):
        self.string = string
        self.riffs, total = self.get_prelude(stream)

        self.refs = {}
        self.headers = {}
        self.stills = {}
        self.assets = {}

        self.palette = None
        self.root = None
        self.junk = None

    def parse(self, stream):
        ################ Asset headers ###################################
        logging.info("(@0x{:012x}) CxtData(): Reading asset headers...".format(stream.tell()))
        end = stream.tell() + read_riff(stream)
        chunk = read_chunk(stream)

        while chunk["code"] == 'igod':
            if Datum(stream).d != ChunkType.HEADER:
                break

            if not self.get_header(stream, chunk): break
            chunk = read_chunk(stream)

        ################ Minor assets ##################################
        logging.info("(@0x{:012x}) CxtData(): Reading minor assets...".format(stream.tell()))

        while stream.tell() < end:
            if chunk_int(chunk):
                logging.debug("(@0x{:012x}) CxtData(): Accepted chunk {} (0x{:04x} bytes)".format(
                    stream.tell(), chunk["code"], chunk["size"])
                )

                self.get_minor_asset(stream, chunk) # updates self.assets
                chunk = read_chunk(stream)

            # TODO: Properly throw away asset links (or understand them)
            while not chunk_int(chunk):
                logging.debug("(@0x{:012x}) CxtData(): Throwing away chunk {} (0x{:04x} bytes)".format(
                    stream.tell(), chunk["code"], chunk["size"])
                )

                Array(stream, bytes=chunk["size"]).log()
                if stream.tell() >= end:
                    break

                chunk = read_chunk(stream)

        logging.info("(@0x{:012x}) CxtData(): Parsed asset headers and minor assets!".format(stream.tell()))

    def majors(self, stream):
        ################# Major assets ###################################
        logging.info("(@0x{:012x}) CxtData(): Reading major assets ({} RIFFs)...".format(stream.tell(), self.riffs-1))
        for i in range(self.riffs-1):
            read_riff(stream)
            self.assets.update(self.get_major_asset(stream))

            logging.debug("(@0x{:012x}) CxtData(): Read RIFF {} of {}".format(stream.tell(), i+1, self.riffs-1))

        ################# Junk data ######################################
        self.junk = stream.read()
        if len(self.junk) > 0:
            logging.warning("Found {} bytes at end of file".format(len(self.junk)))

        logging.info("(@0x{:012x}) CxtData(): Parsed entire context!".format(stream.tell()))

    def get_prelude(self, stream):
        stream.seek(0)

        assert stream.read(4) == b'II\x00\x00', "Incorrect context file signature"
        struct.unpack("<L", stream.read(4))[0]
        riffs = struct.unpack("<L", stream.read(4))[0]
        total = struct.unpack("<L", stream.read(4))[0]
        
        return riffs, total

    def get_header(self, stream, chunk):
        type = Datum(stream)

        if type.d == HeaderType.LINK:
            stream.seek(stream.tell() - 8)
            return False
        if type.d == HeaderType.PALETTE:
            logging.debug(
                "(@0x{:012x}) CxtData.get_header(): Found context palette (0x{:04x} bytes)".format(stream.tell(), 0x300)
            )

            assert not self.palette # We cannot have more than 1 palette
            self.palette = stream.read(0x300)
            value_assert(Datum(stream).d, 0x00, "end-of-chunk flag")
        elif type.d == HeaderType.ROOT:
            logging.debug("(@0x{:012x}) CxtData.get_header(): Found context root".format(stream.tell()))
            assert not self.root # We cannot have more than 1 root
            self.root = Array(stream, bytes=chunk["size"] - 8) # We read 2 datums
        elif type.d == HeaderType.ASSET or type.d == HeaderType.FUNC:
            contents = [AssetHeader(stream, size=chunk["size"]-12, string=self.string)]

            if contents[0].type.d == AssetType.STG:
                contents += contents[0].child

            for header in contents:
                logging.debug("(@0x{:012x}) CxtData.get_header(): Found asset header {}".format(stream.tell(), header))
                self.headers.update({header.id.d: header})

                # TODO: Deal with shared assets.
                if header.ref and not isinstance(header.ref.d, int):
                    # Actual data is in another chunk
                    for ref in header.ref.d.id(string=True):
                        self.refs.update({ref: header})
                else: # All needed data is here in the header
                    self.assets.update(self.make_structured_asset(
                        header, header.child if type.d == HeaderType.FUNC else None)
                    )

                if type.d == HeaderType.FUNC:
                    logging.info("CxtData.get_header(): Found bytecode >>> {}".format(header))
                    logging.info(pprint.pformat(header.data.datums))

            value_assert(Datum(stream).d, 0x00, "end-of-chunk flag")
        elif type.d == HeaderType.UNK_D:
            logging.warning("CxtData.get_header(): Found unknown header type 0x0010")
            stream.seek(stream.tell() + chunk["size"] - 0x04)
        else:
            raise TypeError("Unknown header type: {}".format(type))

        return True

    def get_minor_asset(self, stream, chunk):
        header = self.refs[chunk_int(chunk)]
        logging.debug("(@0x{:012x}) CxtData.get_minor_asset(): {}".format(stream.tell(), header))

        if header.type.d == AssetType.IMG:
            self.assets.update(self.make_structured_asset(header, Image(stream, size=chunk["size"])))
        elif header.type.d == AssetType.SND:
            if not header.id.d in self.assets:
                self.assets.update(self.make_structured_asset(header, Sound()))

            self.assets[header.id.d]["asset"].append(stream, size=chunk["size"])
        elif header.type.d == AssetType.SPR:
            if header.id.d not in self.assets:
                self.assets.update(self.make_structured_asset(header, Sprite()))
                        
            self.assets[header.id.d]["asset"].append(stream, size=chunk["size"])
        elif header.type.d == AssetType.FON:
            if header.id.d not in self.assets:
                self.assets.update(self.make_structured_asset(header, Font()))

            self.assets[header.id.d]["asset"].append(stream, size=chunk["size"])
        elif header.type.d == AssetType.MOV:
            if header.id.d not in self.stills:
                self.stills.update({header.id.d: [[], []]})

            d = Datum(stream) # Read the movie frame header
            if d.d == ChunkType.MOVIE_FRAME:
                self.stills[header.id.d][0].append(MovieFrame(stream, size=chunk["size"]-0x04))
            elif d.d == ChunkType.MOVIE_HEADER:
                self.stills[header.id.d][1].append(Array(stream, bytes=chunk["size"]-0x04))
            else:
                raise ValueError("Unknown header type in movie still area: {}".format(d.d))
        else:
            raise TypeError("Unhandled asset type found in first chunk: {}".format(header.type.d))

    def get_major_asset(self, stream):
        chunk = read_chunk(stream)
        header = self.refs[chunk_int(chunk)]
        logging.debug("(@0x{:012x}) CxtData.get_major_asset: {}".format(stream.tell(), header))

        if header.type.d == AssetType.MOV:
            return self.make_structured_asset(header, Movie(stream, header, chunk, stills=self.stills.get(header.id.d)))
        elif header.type.d == AssetType.SND:
            return self.make_structured_asset(header, Sound(stream, header, chunk))
        else:
            raise TypeError("Unhandled major asset type: {}".format(header.type.d))

    def export(self, directory):
        for id, asset in self.assets.items():
            self.export_structured_asset(directory, asset, id)

        if self.junk and len(self.junk) > 0:
            with open(os.path.join(directory, "junk"), 'wb') as f:
                f.write(self.junk)

    def export_structured_asset(self, directory, asset, id):
        logging.info("CxtData.export_structured_asset(): Exporting asset {}".format(id))
        logging.debug(" >>> {}".format(asset["header"]))

        path = os.path.join(directory, str(id))
        Path(path).mkdir(parents=True, exist_ok=True)

        with open(os.path.join(path, "{}.txt".format(id)), 'w') as header:
            print(repr(asset["header"]), file=header)
            for datum in asset["header"].data.datums:
                print(repr(datum), file=header)

        # TODO: Get palette handling generalized.
        if asset["asset"]: asset["asset"].export(path, str(id), palette=self.palette, with_header=True)

    @staticmethod
    def make_structured_asset(header, asset):
        return {header.id.d: {"header": header, "asset": asset}}


############### SYSTEM PARSER (BOOT.STM)  ################################

class System(Object):
    def __init__(self, directory, stream, string):
        self.directory = directory
        self.string = string

        self.contexts = {}
        self.assets = {}
        self.headers = {}

        end = stream.tell() + read_riff(stream)
        chunk = read_chunk(stream)

        logging.debug("Reading header information...")
        header = Array(stream, datums=3)
        stream.read(2) # Why is a random 00 13 hanging around?

        header.datums += Array(stream, datums=5).datums
        self.name = header.datums[2].d

        unk = Array(stream, datums=2*3) # 401 402 403 (?)

        # Read resource information
        logging.debug("Reading resource information...")
        self.resources = []
        type = Datum(stream)
        while type.d == RecordType.RES_NAME:
            name = Datum(stream)

            value_assert(Datum(stream).d, RecordType.RES_ID)
            id = Datum(stream)

            logging.debug("Found resource {} ({})".format(id.d, name.d))
            self.resources.append((id, name))
            type = Datum(stream)

        # Read file headers
        logging.debug("Reading file headers...")
        value_assert(type.d, BootRecord.FILES_1, "root signature")
        files = []
        while True: # breaking condition is below
            type = Datum(stream)
            refs = []
            while type.d == RecordType.CXT:
                refs.append(Datum(stream).d)
                type = Datum(stream)

            if type.d == 0x0000:
                break

            if type.d == 0x0003:
                refstring = None
                value_assert(Datum(stream).d, 0x0004, "file signature")

                filenum = Datum(stream)
                value_assert(Datum(stream).d, 0x0005, "file signature")
                assert Datum(stream).d == filenum.d

                if string:
                    value_assert(Datum(stream).d, 0x0bb8, "string signature")
                    refstring = Datum(stream)
            else:
                raise ValueError("Received unexpected file signature: {}".format(type.d))

            logging.debug("Found file {}{} (refs: {})".format(
                filenum.d, " ({})".format(refstring.d) if string else "", refs)
            )

            files.append(
                {"refs": refs, "filenum": filenum.d, "string": refstring.d if string else None}
            )

        logging.debug("Categorizing data files...")
        is_data = {}
        value_assert(Datum(stream).d, BootRecord.FILES_2)
        type = Datum(stream)
        while type.d == RecordType.FILE_1:
            value_assert(Datum(stream).d, 0x0009)
            file = Datum(stream)
            value_assert(Datum(stream).d, 0x0004)
            assert file.d == Datum(stream).d

            logging.debug("Referenced data file {}".format(file.d))
            type = Datum(stream)

        value_assert(type.d, 0x0000)

        # Now link asset IDs to file names
        value_assert(Datum(stream).d, BootRecord.FILES_3)
        self.files = {}
        type = Datum(stream)

        while type.d == RecordType.FILE_3:
            value_assert(Datum(stream).d, 0x002b)
            id = Datum(stream)
            value_assert(Datum(stream).d, 0x002d)

            filetype = Datum(stream)
            filename = Datum(stream)

            logging.debug("Read file link {} ({})".format(filename.d, id.d))
            self.files.update(
                # INSTALL.CXT has ID 3
                {id.d: dict({"file": filename.d}, **(files.pop(0) if id.d != 0x0003 else {}))}
            )
            type = Datum(stream)

        value_assert(type.d, 0x0000)

        # Link RIFF asset chunks
        value_assert(Datum(stream).d, BootRecord.RIFF)
        self.riffs = []

        type = Datum(stream)
        while type.d == RecordType.RIFF:
            value_assert(Datum(stream).d, 0x002a)
            asset = Datum(stream)
            value_assert(Datum(stream).d, 0x002b)
            id = Datum(stream)
            value_assert(Datum(stream).d, 0x002c)
            loc = Datum(stream)

            logging.debug("Read RIFF for asset {} ({}:0x{:08x})".format(asset.d, self.files[id.d]["file"], loc.d))

            # Note that this really should be a dictionary.
            self.riffs.append({"assetid": asset.d, "fileid": id.d, "offset": loc.d})
            type = Datum(stream)

        value_assert(type.d, 0x0000)

        # Link resource data
        self.cursors = {}
        value_assert(Datum(stream).d, BootRecord.CURSOR)
        for _ in range(Datum(stream).d, Datum(stream).d): # start and stop
            value_assert(Datum(stream).d, RecordType.CURSOR)
            value_assert(Datum(stream).d, 0x0001)
            id = Datum(stream)
            unk = Datum(stream)
            name = Datum(stream)

            logging.debug("Read cursor {}: {} ({})".format(id.d, name.d, id.d))
            self.cursors.update({id.d: [unk.d, name.d]})

        self.footer = stream.read()
        logging.debug(pprint.pformat(self.files))

    def parse(self, export):
        riffs = self.riffs
        riffs.reverse()

        logging.info("System.parse(): Parsing full title: {}".format(self.name))
        for id, entry in self.files.items():
            try:
                cxtname = os.path.join(self.directory, entry["file"])
                with open(cxtname, mode='rb') as f:
                    stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
                    logging.info("System.parse(): Opened context {} ({})".format(entry["file"], id))

                    cxt = Context(stream, self.string)
                    # Process the root first (if it exists).
                    if entry.get("filenum"):
                        logging.debug("System.parse(): ({}) Parsing root entry...".format(entry["file"]))
                        riff = riffs.pop()

                        self.contexts.update({entry["filenum"]: cxt})
                        cxt.parse(stream)
                        self.headers.update(cxt.headers)

                        if export: cxt.export(export)

                    # Now process all major assets in this file.
                    for i in range(cxt.riffs-1):
                        riff = riffs.pop()
                        header = self.headers[riff["assetid"]]

                        logging.debug(
                            "System.parse(): ({}) Parsing major asset {}@0x{:012x} ({} of {})...".format(
                                entry["file"], riff["assetid"], riff["offset"], i+1, cxt.riffs-1
                            )
                        )
                        logging.debug(" >>> {} ".format(header))

                        if stream.tell() % 2 == 1:
                            stream.read(1)

                        value_assert(stream.tell(), riff["offset"], "stream position")
                        read_riff(stream)

                        asset = self.contexts[header.filenum.d].get_major_asset(stream)[riff["assetid"]]
                        if export: self.contexts[header.filenum.d].export_structured_asset(export, asset, riff["assetid"])
            except Exception as e:
                log_location(cxtname, stream.tell())
                traceback.print_exc()
                input("Press return to continue...")


############### INTERACTIVE LOGIC  #######################################

def main(input, string, export):
    stream = None
    if os.path.isdir(input):
        with open(os.path.join(input, "boot.stm"), mode='rb') as f:
            stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)

            try:
                stm = System(input, stream, string)
                stm.parse(export)
            except Exception as e:
                log_location(os.path.join(input, "boot.stm"), stream.tell())
                raise
    elif os.path.isfile(input):
        with open(input, mode='rb') as f:
            stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)

            if input[-3:].lower() == "cxt":
                logging.info("Received single context, operating in standalone mode")

                try:
                    cxt = Context(stream, string)
                    cxt.parse(stream)
                    cxt.majors(stream)
                except Exception as e:
                    log_location(input, stream.tell())
                    raise

                if export: cxt.export(export)
            elif os.path.split(input)[1].lower() == "boot.stm":
                if export: logging.warning("Only parsing system information; ignoring export flag")
                System(None, stream, string)
            else:
                raise ValueError(
                    "Ambiguous input file extension. Ensure a numeric context (CXT) or system (STM) file has been passed."
                )
    else:
        raise ValueError("The path specified is invalid or does not exist.")

def log_location(file, position):
    logging.error("Exception at {}:0x{:012x}".format(file, position))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cxt", description="Parse asset structures and extract assets from Media Station, Inc. games"
    )

    parser.add_argument(
        "input", help="Pass a context (CXT) or system (STM) filename to process the file, or pass a game data directory to process the whole game."
    )

    parser.add_argument(
        '-s', "--string", default=False, action='store_true',
        help="Specify that context datafiles have embedded debug strings (Tonka Garage)"
    )

    parser.add_argument(
        '-e', "--export", default=None,
        help="Specify the location for exporting assets. Assets are not exported if not provided"
    )

    logging.basicConfig(level=logging.DEBUG)
    args = parser.parse_args()

    main(args.input, args.string, args.export)
