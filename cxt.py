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

class ChunkType(IntEnum):
    HEADER         = 0x000d,
    IMAGE          = 0x0018,
    MOVIE_ROOT     = 0x06a8,
    MOVIE_FRAME    = 0x06a9,
    MOVIE_HEADER   = 0x06aa,

class HeaderType(IntEnum):
    LEGACY  = 0x000d,
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

version = None

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
    def __init__(self, stream, peek=False):
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
            self.d = Ref(stream)
        else:
            stream.seek(self.start)
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
    def __init__(self, stream):
        self.data = stream.read(4).decode("utf-8")

    def id(self, string=False):
        return int(self.data[1:], 16) if string else self.data

    def __repr__(self):
        return "<Ref: {} ({:0>4d})>".format(self.id(), self.id(string=True))

class Bytecode(Object):
    def __init__(self, stream, prologue):
        self.id = None
        if not prologue: # for 0x0017 asset headers
            self.type = Datum(stream)
            Datum(stream)
            # if self.type.d == 0x0005:
            Datum(stream)

        start = stream.tell()
        initial = Datum(stream)
        logging.debug("Bytecode(): Expecting {} bytes".format(initial.d))
        self.code = self.chunk(initial, stream)
        self.length = stream.tell() - start
        value_assert(self.length - 0x006, self.code[0].d, "length")

    def chunk(self, size, stream):
        code = [size, []]
        start = stream.tell()
        while stream.tell() - start < size.d:
            code[1].append(self.entity(Datum(stream), stream, end=start + size.d))

        return code

    def entity(self, token, stream, end, string=False):
        if token.t == 0x0004:
            return self.chunk(token, stream)

        if token.d == 0x0067:
            code = [token, []]
            for _ in range(3):
                code[1].append(self.entity(Datum(stream), stream, end))
                if stream.tell() >= end:
                    break
        elif token.d == 0x0066:
            code = [token, []]
            for i in range(2):
                code[1].append(self.entity(Datum(stream), stream, end, string=not i))
                if stream.tell() >= end:
                    break
        elif token.d == 0x0065:
            code = [token, []]
            code[1].append(self.entity(Datum(stream), stream, end))
        elif token.d == 0x009a and string: # character string
            size = Datum(stream)
            code = [stream.read(size.d)]
        else:
            code = [token]

        return code

    def export(self, directory, filename, **kwargs):
        with open(os.path.join(directory, filename + ".txt"), 'w') as bytecode:
            pprint.pprint(self.code, stream=bytecode)

    def __repr__(self):
        return "<Bytecode: {} bytes, {} chunks>".format(self.length, len(self.code))

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
        for _ in range(size.d):
            stream.read(2)
            self.points.append(Point(stream))

    def __repr__(self):
        return "<Polygon: points: {}>".format(len(self.points))

class Array(Object):
    def __init__(self, stream, bytes=None, datums=None, stop=None):
        self.datums = []
        start = stream.tell()

        if bytes == 0 and not datums and not stop:
            return
        if not datums and not bytes and not stop:
            raise AttributeError("Creating an array requires providing a bytes size or a stop parameter.")

        while True:
            d = Datum(stream)
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
        return "<Array: size: {:0>4d}; bytes: {:0>4d}>".format(len(self.datums), self.bytes)

class AssetHeader(Object):
    def __init__(self, stream, stage=False):
        logging.debug("AssetHeader(): Beginning header read")

        self.filenum = Datum(stream)
        self.type = Datum(stream)
        self.id = Datum(stream)
        self.name = None
        self.ref = []
        self.triggers = []
        self.mouse = []

        self.raw = {}
        type = Datum(stream)
        while type.d != 0x0000:
            d = None
            logging.debug("(@0x{:012x}) AssetHeader(): Read type 0x{:04x}".format(stream.tell(), type.d))

            if type.d == 0x0017: # TMR, MOV
                logging.debug("--- BEGIN BYTECODE ---")
                self.triggers = Bytecode(stream, prologue=False)
                pprint.pprint(self.triggers.code)
                logging.debug(self.triggers)
                logging.debug("--- END BYTECODE ---")
            elif type.d == 0x0019: # STG, IMG, SPR, MOV, TXT, CAM, CVS
                d = Datum(stream)
            elif type.d == 0x001a: # SND, MOV
                d = Datum(stream)
            elif type.d == 0x001b: # SND, IMG, SPR, MOV, FON
                if self.type.d == AssetType.MOV:
                    for _ in range(2):
                        self.ref.append(Datum(stream))
                        Datum(stream)

                    self.ref.append(Datum(stream))
                else: self.ref = [Datum(stream)]
            elif type.d == 0x001c: # STG, IMG, HSP, SPR, MOV, TXT, CAM, CVS
                self.bbox = Datum(stream)
            elif type.d == 0x001d:
                self.poly = Polygon(stream)
            elif type.d == 0x001e: # STG, IMG, HSP, SPR, MOV, TXT, CAM, CVS
                d = Datum(stream)
            elif type.d == 0x001f: # IMG, HSP, SPR, MOV, TXT, CVS
                d = Datum(stream)
            elif type.d == 0x0020: # IMG, SPR, CVS
                d = Datum(stream)
            elif type.d == 0x0021: # SND
                d = Datum(stream)
            elif type.d == 0x0022: # SCR, TXT, CVS
                d = Datum(stream)
            elif type.d == 0x0024: # SPR
                d = Datum(stream)
            elif type.d == 0x0032: # IMG, SPR
                d = Datum(stream)
            elif type.d == 0x0033: # SND, MOV
                self.chunks = Datum(stream)
                self.rate = Datum(stream)
            elif type.d == 0x0037:
                d = Datum(stream)
            elif type.d == 0x0258: # TXT
                d = Datum(stream)
            elif type.d == 0x0259: # TXT
                d = Datum(stream)
            elif type.d == 0x025a: # TXT
                d = Datum(stream)
            elif type.d == 0x025b: # TXT
                d = Datum(stream)
            elif type.d == 0x025f: # TXT
                d = Datum(stream)
            elif type.d == 0x0263: # TXT
                Array(stream, stop=(DatumType.UINT16, 0x0000))
                stream.seek(stream.tell() - 4)
            elif type.d == 0x03e8: # SPR
                self.chunks = Datum(stream)
            elif type.d == 0x03e9: # SPR
                self.mouse.append(Array(stream, datums=3))
            elif type.d == 0x03ea:
                d = Datum(stream)
            elif type.d == 0x03eb: # IMG, SPR, TXT, CVS
                d = Datum(stream)
            elif type.d == 0x03ec:
                d = Datum(stream)
            elif type.d == 0x03ed:
                try:
                    Array(stream, stop=(DatumType.UINT16, 0x0011))
                    stream.seek(stream.tell() - 8)
                except:
                    stream.seek(stream.tell() - 4)
                    return
                # d = Datum(stream)
            elif type.d == 0x03f4:
                d = Datum(stream)
            elif type.d == 0x0517:
                try:
                    Array(stream, stop=(DatumType.UINT16, 0x0011))
                    stream.seek(stream.tell() - 8)
                except:
                    stream.seek(stream.tell() - 4)
            elif type.d == 0x05aa: # PAL
                self.palette = stream.read(0x300)
            elif type.d == 0x05dc: # IMG, SPR, MOV, CVS
                d = Datum(stream)
            elif type.d == 0x05dd:
                d = Datum(stream)
            elif type.d == 0x05de: # IMG
                self.x = Datum(stream)
            elif type.d == 0x05df: # IMG
                self.y = Datum(stream)
            elif type.d == 0x060e: # PTH
                self.start = [Datum(stream)]
            elif type.d == 0x060f: # PTH
                self.end = [Datum(stream)]
            elif type.d == 0x0610: # PTH
                d = Datum(stream)
            elif type.d == 0x0611: # PTH
                self.end.append(Datum(stream))
            elif type.d == 0x0612: # PTH
                self.start.append(Datum(stream))
            elif type.d == 0x076f: # CAM
                d = Datum(stream)
            elif type.d == 0x0770: # CAM
                d = Datum(stream)
            elif type.d == 0x0772: # STG
                d = Datum(stream)
                pass
            elif type.d == 0x077b: # IMG
                self.ref = [Datum(stream)] # an integer holding refd asset ID
            elif type.d == 0x0bb8:
                self.name = Datum(stream)
            elif type.d == 0x0001: # SND
                self.encoding = Datum(stream)
            else:
                raise TypeError("AssetHeader(): Unknown field delimiter in header: 0x{:0>4x}".format(type.d))

            if d: self.raw.update({repr(type): d.d})
            if type.d == 0x0000: break

            type = Datum(stream)

        logging.debug("(@0x{:012x}) AssetHeader(): Finished reading asset header".format(stream.tell()))

        if self.type.d == AssetType.STG:
            self.children = []

            value_assert(Datum(stream).d, HeaderType.LINK, "link signature")
            value_assert(Datum(stream).d, self.id.d, "asset id")

            if stage: return # Tonka Raceway has embedded stages!

            type = Datum(stream)
            while type.d == HeaderType.ASSET:
                self.children.append(AssetHeader(stream, stage=True))
                type = Datum(stream)

    def __repr__(self):
        return "<AssetHeader: parent: {}, type: 0x{:0>4x}, id: 0x{:0>4x} ({:0>4d}){}{}>".format(
            self.filenum.d, self.type.d, self.id.d, self.id.d,
            " {}".format([ref.d if isinstance(ref.d, int) else ref.d.id() for ref in self.ref]) if self.ref else "",
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
        self.unks = []

        value_assert(Datum(stream).d, 0x0001)
        self.unks.append(Datum(stream)) # value_assert(Datum(stream).d, 0x0000)
        if is_legacy():
            self.duration = (Datum(stream), Datum(stream)) # milliseconds
            self.dims = Point(None, x=Datum(stream).d, y=Datum(stream).d) # inside bbox
            for _ in range(2):
                self.unks.append(Datum(stream))
            self.index = Datum(stream)
        else:
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
            self.start, self.index.d, ["{:06d}".format(d.d) for d in self.duration], self.dims, pprint.pformat(self.unks)
        )

class MovieHeaderInner(Object):
    def __init__(self, stream):
        self.start = stream.tell()

        value_assert(Datum(stream).d, 0x0028)
        self.dims = Datum(stream)
        unk2 = Datum(stream) # Tonka Raceway: 0x0006
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

        headers = open(os.path.join(directory, "headers.txt"), 'w')
        sound = Sound(encoding=0x0010)

        for i, chunk in enumerate(self.chunks):
            for j, frame in enumerate(chunk["frames"]):
                # Handle the frame headers first
                print(" --- {}-{} ---".format(i, j), file=headers)
                print(repr(frame[0]), file=headers)
                print(" \\\\\ ", file=headers)

                # Now handle the actual frames
                print(repr(frame[1].header), file=headers)

                if frame[1].image:
                    if frame[1].image.header:
                        print ("  |-- Image header --|  ", file=headers)
                        print(repr(frame[1].image.header), file=headers)

                    frame[1].image.export(directory, "{}-{}".format(i, j), fmt=fmt[0], **kwargs)

            if chunk["audio"]:
                sound.append(chunk["audio"])

        sound.export(directory, "sound", fmt=fmt[1], **kwargs)
        headers.close()

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
    def __init__(self, stream=None, chunk=None, **kwargs):
        self.chunks = []
        self.encoding = kwargs.get("encoding")
        if isinstance(self.encoding, Datum):
            self.encoding = self.encoding.d

        # If we provide these arguments, we want to read a while RIFF;
        # otherwise, this is for movie sound that we will add separately.
        if not stream or not chunk:
            return

        self.chunk_count = kwargs.get("chunks")
        logging.debug(" *** Sound(): Expecting {} sound chunks ***".format(self.chunk_count.d))

        asset_id = chunk["code"]
        self.append(stream, chunk["size"])
        for i in range(1, self.chunk_count.d):
            chunk = read_chunk(stream)
            value_assert(chunk["code"], asset_id, "sound chunk label")
            self.append(stream, chunk["size"])
            logging.debug(" ~~ Sound(): Finished chunk {} of {} ~~".format(i+1, self.chunk_count.d))

    def append(self, stream, size=0):
        if isinstance(stream, bytes):
            self.chunks.append(stream)
        else:
            logging.debug("Sound(): Reading sound chunk of size 0x{:04x}".format(size))
            self.chunks.append(stream.read(size))

    def export(self, directory, filename, fmt="wav", **kwargs):
        filename = "{}.{}".format(os.path.join(directory, filename), fmt.lower())

        if fmt.lower() == "raw":
            with open(filename, 'wb') as raw:
                for chunk in self.chunks:
                    raw.write(chunk)
        else:
            if self.encoding and self.encoding == 0x0010:
                command = ['ffmpeg', '-y', '-f', 's16le', '-ar', '11.025k', '-ac', '2', '-i', 'pipe:', filename]
            elif self.encoding and self.encoding == 0x0004:
                # TODO: Fine the proper codec. This ALMOST sounds right.
                command = ['ffmpeg', '-y', '-f', 's16le', '-ar', '22.050k', '-ac', '1', "-acodec", "adpcm_ima_ws", '-i', 'pipe:', filename]
            else:
                raise ValueError("Sound.export(): Received unknown encoding specifier: 0x{:04x}.".format(self.encoding))
                command = ['ffmpeg', '-y', '-f', 's16le', '-ar', '11.025k', '-ac', '2', '-i', 'pipe:', filename]

            with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
                for chunk in self.chunks:
                    process.stdin.write(chunk)

                process.communicate()


############### CONTEXT PARSER (*.CXT)  ##################################

class Context(Object):
    def __init__(self, stream):
        self.riffs, total = self.get_prelude(stream)

        self.functions = {}
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

        if not is_legacy(): # Headers stored in separate chunks
            while chunk["code"] == 'igod':
                if Datum(stream).d != ChunkType.HEADER:
                    break

                if not self.get_header(stream, chunk): break
                chunk = read_chunk(stream)
        else: # Headers stored in one chunk.
            logging.warning("CxtData(): Detected early compiler version; using legacy header lookup")
            value_assert(Datum(stream).d, HeaderType.LEGACY)
            self.get_header(stream, chunk)
            chunk = read_chunk(stream)
            start = stream.tell()

            value_assert(Datum(stream).d, HeaderType.LEGACY)
            while stream.tell() < chunk["size"] + start:
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
            if not is_legacy():
                self.root = Array(stream, bytes=chunk["size"] - 8) # We read 2 datums
            else:
                self.root = Array(stream, stop=(DatumType.UINT16, 0x0011))
                self.root.datums += Array(stream, stop=(DatumType.UINT16, 0x0011)).datums
                self.root.datums += Array(stream, stop=(DatumType.UINT16, 0x0011)).datums
                stream.seek(stream.tell() - 4)
        elif type.d == HeaderType.ASSET or (type.d == HeaderType.ROOT and is_legacy()):
            contents = [AssetHeader(stream)]

            if contents[0].type.d == AssetType.STG:
                contents += contents[0].children

            for header in contents:
                logging.debug("(@0x{:012x}) CxtData.get_header(): Found asset header {}".format(stream.tell(), header))
                self.headers.update({header.id.d: header})

                # TODO: Deal with shared assets.
                if header.ref and not isinstance(header.ref[0].d, int):
                    # Actual data is in another chunk
                    for ref in header.ref:
                        self.refs.update({ref.d.id(string=True): header})
                else: # All needed data is here in the header
                    self.assets.update(self.make_structured_asset(
                        header, header.targets if type.d == HeaderType.FUNC else None)
                    )

            if contents[0].type.d != AssetType.STG and not is_legacy():
                value_assert(Datum(stream).d, 0x00, "end-of-chunk flag")

                if stream.tell() % 2 == 1:
                    stream.read(1)
        elif type.d == HeaderType.FUNC:
            Datum(stream) # file ID
            self.functions.update({Datum(stream).d + 0x4dbc: Bytecode(stream, prologue=True)})
            if not is_legacy():
                value_assert(Datum(stream).d, 0x00, "end-of-chunk flag")
        elif type.d == 0x0000:
            raise ValueError("Leftover end-of-chunk flags should not be present")
            # return True
        else:
            raise TypeError("Unknown header type: {}".format(type))

        return True

    def get_minor_asset(self, stream, chunk):
        header = self.refs[chunk_int(chunk)]
        logging.debug("(@0x{:012x}) CxtData.get_minor_asset(): {}".format(stream.tell(), header))

        if header.type.d == AssetType.IMG or header.type.d == AssetType.CAM:
            self.assets.update(self.make_structured_asset(header, Image(stream, size=chunk["size"])))
        elif header.type.d == AssetType.SND:
            if not header.id.d in self.assets:
                self.assets.update(self.make_structured_asset(header, Sound(encoding=header.encoding)))

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
            return self.make_structured_asset(header, Sound(stream, chunk, chunks=header.chunks, encoding=header.encoding))
        else:
            raise TypeError("Unhandled major asset type: {}".format(header.type.d))

    def export(self, directory):
        for id, asset in self.assets.items():
            self.export_structured_asset(directory, asset, id)

        for id, func in self.functions.items():
            self.export_function(directory, func, id)

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

        # TODO: Get palette handling generalized.
        if asset["asset"]: asset["asset"].export(path, str(id), palette=self.palette, with_header=True)

    def export_function(self, directory, func, id):
        logging.info("CxtData.export_function()(): Exporting function {}".format(id))

        path = os.path.join(directory, str(id))
        Path(path).mkdir(parents=True, exist_ok=True)

        func.export(path, str(id))

    @staticmethod
    def make_structured_asset(header, asset):
        return {header.id.d: {"header": header, "asset": asset}}


############### SYSTEM PARSER (BOOT.STM)  ################################

class System(Object):
    def __init__(self, argv, stream):
        self.argv = argv

        global version
        version = {"number": (0, 0, 0), "string": None}

        self.resources = {}
        self.contexts = {}
        self.assets = {}
        self.headers = {}
        self.files = {}
        self.riffs = []
        self.cursors = {}

        self.name = None
        self.source = None

        end = stream.tell() + read_riff(stream)
        chunk = read_chunk(stream)
        files = []

        logging.debug("System(): Reading title information...")
        value_assert(Datum(stream).d, 0x0001)

        type = Datum(stream)
        while type.d != 0x0000:
            if type.d == 0x190: # No metadata: LIONKING
                self.name = Datum(stream)
                stream.read(2)
                version = {
                    "number": (Datum(stream).d, Datum(stream).d, Datum(stream).d),
                    "string": Datum(stream)
                }
                self.source = Datum(stream)

                logging.info("System(): 1. Detected title: {} (compiler version {:01d}.{:02d}.{:02d}{})".format(
                    self.name.d, *[digit for digit in version["number"]], " LEGACY" if is_legacy() else "")
                )
            elif type.d == 0x191 or type.d == 0x192 or type.d == 0x193:
                logging.warning("System(): 2. Detected unknown field 0x{:04x}: 0x{:04x}".format(type.d, Datum(stream).d))
            elif type.d == 0x0bba:
                name = Datum(stream)
                value_assert(Datum(stream).d, 0x0bbb)
                id = Datum(stream)

                logging.debug("System(): 3. Found resource {} ({})".format(id.d, name.d))
                self.resources.update({id.d: name})
            elif type.d == 0x0002:
                token = Datum(stream)
                while True: # breaking condition is below
                    refs = []

                    while token.d == 0x0006:
                        refs.append(Datum(stream).d)
                        token = Datum(stream)

                    if token.d == 0x0000:
                        break
                    elif token.d == 0x0003:
                        value_assert(Datum(stream).d, 0x0004)

                        filenum = Datum(stream)
                        value_assert(Datum(stream).d, 0x0005)
                        assert Datum(stream).d == filenum.d

                        token = Datum(stream)
                        if token.d == 0x0bb8:
                            name = Datum(stream)
                            token = Datum(stream)
                        else:
                            name = None
                    else:
                        raise ValueError("Received unexpected file signature: {}".format(type.d))

                    logging.debug("System(): 4. Found file {}{} (refs: {})".format(
                        filenum.d, " ({})".format(name.d) if name else "", refs)
                    )

                    files.append(
                        {"refs": refs, "filenum": filenum.d, "name": name.d if name else None}
                    )
            elif type.d == 0x0007:
                token = Datum(stream)
                while token.d == 0x0008:
                    value_assert(Datum(stream).d, 0x0009)
                    file = Datum(stream)
                    value_assert(Datum(stream).d, 0x0004)
                    assert file.d == Datum(stream).d

                    logging.debug("System(): 5. Referenced data file {}".format(file.d))
                    token = Datum(stream)

                value_assert(token.d, 0x0000)
            elif type.d == 0x000a:
                token = Datum(stream)
                while token.d == 0x0029:
                    value_assert(Datum(stream).d, 0x002b)
                    id = Datum(stream)
                    value_assert(Datum(stream).d, 0x002d)

                    filetype = Datum(stream)
                    filename = Datum(stream)

                    self.files.update(
                        # INSTALL.CXT has ID 3
                        {id.d: dict({"file": filename.d}, **(files.pop(0) if id.d != 0x0003 else {}))}
                    )

                    logging.debug("System(): 6. Read file link {} ({})".format(filename.d, id.d))
                    token = Datum(stream)

                value_assert(token.d, 0x0000)
            elif type.d == 0x000b:
                token = Datum(stream)
                while token.d == 0x0028:
                    value_assert(Datum(stream).d, 0x002a)
                    asset = Datum(stream)
                    value_assert(Datum(stream).d, 0x002b)
                    id = Datum(stream)
                    value_assert(Datum(stream).d, 0x002c)
                    loc = Datum(stream)

                    logging.debug("System(): 7. Read RIFF for asset {} ({}:0x{:08x})".format(asset.d, self.files[id.d]["file"], loc.d))

                    # Note that this really should be a dictionary.
                    self.riffs.append({"assetid": asset.d, "fileid": id.d, "offset": loc.d})
                    token = Datum(stream)

                value_assert(token.d, 0x0000)
            elif type.d == 0x0015:
                value_assert(Datum(stream).d, 0x0001)
                id = Datum(stream)
                unk = Datum(stream)
                name = Datum(stream)

                logging.debug("System(): 8. Read cursor {}: {} ({})".format(id.d, name.d, id.d))
                self.cursors.update({id.d: [unk.d, name.d]})

            type = Datum(stream)

        self.footer = stream.read()
        logging.debug(pprint.pformat(self.files))

    def parse(self):
        riffs = self.riffs
        riffs.reverse()

        logging.info("System.parse(): Parsing full title{}!".format(": {}".format(self.name.d) if self.name else ""))
        for id, entry in self.files.items():
            try:
                cxtname = resolve_filename(self.argv.input, entry["file"])
                if os.path.getsize(cxtname) == 0x10: # Some legacy titles have an empty root entry
                    logging.warning("System.parse(): Skipping empty context {} ({})".format(entry["file"], id))
                    continue

                with open(cxtname, mode='rb') as f:
                    stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
                    logging.info("System.parse(): Opened context {} ({})".format(entry["file"], id))

                    cxt = Context(stream)
                    # Process the root first (if it exists).
                    if entry.get("filenum"):
                        logging.debug("System.parse(): ({}) Parsing root entry...".format(entry["file"]))
                        riff = riffs.pop()

                        self.contexts.update({entry["filenum"]: cxt})
                        cxt.parse(stream)
                        self.headers.update(cxt.headers)

                        if self.argv.export:
                            cxt.export(os.path.join(self.argv.export, str(entry["filenum"]) if self.argv.separate else ""))

                    # Now process all major assets in this file.
                    if not self.argv.first_chunk_only:
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
                            if self.argv.export:
                                self.contexts[header.filenum.d].export_structured_asset(
                                    os.path.join(self.argv.export, str(entry["filenum"]) if self.argv.separate else ""),
                                    asset, riff["assetid"]
                                )
            except Exception as e:
                log_location(cxtname, stream.tell())
                traceback.print_exc()
                input("Press return to continue...")


############### INTERACTIVE LOGIC  #######################################

def main(args):
    stream = None
    if os.path.isdir(args.input):
        with open(resolve_filename(args.input, "boot.stm"), mode='rb') as f:
            stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)

            try:
                stm = System(args, stream)
                stm.parse()
            except Exception as e:
                log_location(os.path.join(args.input, "boot.stm"), stream.tell())
                raise
    elif os.path.isfile(args.input):
        with open(args.input, mode='rb') as f:
            stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)

            if args.input[-3:].lower() == "cxt":
                logging.info("Received single context, operating in standalone mode. Make sure all flags are properly set!")

                try:
                    cxt = Context(stream)
                    cxt.parse(stream)

                    if not args.first_chunk_only:
                        cxt.majors(stream)
                except Exception as e:
                    log_location(args.input, stream.tell())
                    raise

                if args.export: cxt.export(args.export)
            elif os.path.split(args.input)[1].lower() == "boot.stm":
                if args.export:
                    logging.warning("Only parsing system information; ignoring export flag")

                try:
                    System(None, stream)
                except Exception as e:
                    log_location(args.input, stream.tell())
                    raise
            else:
                raise ValueError(
                    "Ambiguous input file extension. Ensure a numeric context (CXT) or system (STM) file has been passed."
                )
    else:
        raise ValueError("The path specified is invalid or does not exist.")

def resolve_filename(directory, filename):
    # I don't need a recursive listing (i.e. checking directories for inconsistency)
    entries = {entry.lower(): entry for entry in os.listdir(directory)}
    if not entries.get(filename.lower()):
        open(os.path.join(directory, filename)) # raise exception

    return os.path.join(directory, entries.get(filename.lower()))

def is_legacy():
    return version and version["number"][1] < 2

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
        '-s', "--separate", default=None, action="store_true",
        help="When exporting, create a new subdirectory for each context. By default, a flat structure with all asset ID directories will be created."
    )

    parser.add_argument(
        "-f", "--first-chunk-only", default=None, action="store_true",
        help="Only parse the first chunk, containing asset headers, functions, and minor assets."
    )
    parser.add_argument(
        '-e', "--export", default=None,
        help="Specify the location for exporting assets. Assets are not exported if not provided"
    )

    logging.basicConfig(level=logging.DEBUG)
    args = parser.parse_args()

    main(args)
