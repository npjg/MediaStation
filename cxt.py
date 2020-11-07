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

import PIL.Image as PILImage

class ChunkType(IntEnum):
    HEADER = 0x000d,
    IMAGE  = 0x0018,
    MOV_1  = 0xa8a4,
    MOV_2  = 0x06a9,
    MOV_3  = 0x06aa

class HeaderType(IntEnum):
    ROOT  = 0x000e,
    ASSET = 0x0011,
    LINK  = 0x0013,
    MOV_H = 0x06aa,
    MOV_V = 0x06a9,

class AssetType(IntEnum):
    SCR  = 0x0001,
    STG  = 0x0002,
    IMG  = 0x0007,
    MOV  = 0x0016,
    HSP  = 0x000b,
    TMR  = 0x0006,
    SND  = 0x0005,
    PAL  = 0x0017,
    TXT  = 0x001a,
    FON  = 0x001b,
    CVS  = 0x001e,
    SPR  = 0x000e

class DatumType(IntEnum):
    UINT8   = 0x0002,
    UINT16  = 0x0003,
    UINT32  = 0x0004,
    UINT16_2  = 0x0006,
    UINT64  = 0x0009,
    SINT16  = 0x0010,
    SINT64  = 0x0011,
    STRING  = 0x0012,
    POINT   = 0x000f,
    POINT_2 = 0x000e,
    PALETTE = 0x05aa,
    REF     = 0x001b,
    BBOX    = 0x000d,
    POLY    = 0x001d

def value_assert(m, target, type="value", warn=False):
    s = 0
    ax = m
    try:
        s = m.tell()
        ax = m.read(len(target))
    except AttributeError:
        pass

    msg = "(@ +0x{:0>4x}) Expected {} {}{}, received {}{}".format(
        s, type, target, " (0x{:0>4x})".format(target) if isinstance(target, int) else "",
        ax, " (0x{:0>4x})".format(ax) if isinstance(ax, int) else "",
    )
    if warn and ax != target:
        logging.warning(msg)
    else:
        assert ax == target, msg

        return ax

def chunk_assert(m, target, warn=False):
    value_assert(m, target, "chunk", warn)

def align(m):
    if m.tell() % 2 == 1:
        m.read(1)


# Internal representations

class Object:
    def __format__(self, spec):
        return self.__repr__()

class Chunk(Object):
    def __init__(self, m):
        self.start = m.tell()
        self.code = m.read(4).decode("utf-8")
        self.size = struct.unpack("<L", m.read(4))[0]

        self.data = io.BytesIO(m.read(self.size))
        align(m)

    def __repr__(self):
        return "<Chunk: 0x{:0>12x}; id: {}, size: 0x{:0>6x}>".format(
            self.start, self.code, self.size
        )

class Datum(Object):
    def __init__(self, m, parent=None):
        # TODO: All this processing is unnecessary once I have the format
        # completely figured out. All of this complicated type-checking can be
        # replaced with assertion.
        self.s = m.tell()
        self.d = None
        self.t = struct.unpack("<H", m.read(2))[0]

        if self.t == DatumType.UINT8:
            self.d = int.from_bytes(m.read(1), byteorder='little')
        elif self.t == DatumType.UINT16 or self.t == DatumType.UINT16_2:
            self.d = struct.unpack("<H", m.read(2))[0]

            if self.d == DatumType.REF:
                # Make sure it is truly a reference and keep as int if not
                try:
                    chunk_assert(m, b'\x1b\x00')
                except AssertionError:
                    m.seek(m.tell() - 2)
                    return

                m.seek(m.tell() - 2)

                # Separate out movie references from plain references.
                self.t = self.d
                try:
                    if parent.datums[1].d == AssetType.MOV:
                        self.d = MovieRef(m)
                    else:
                        self.d = Ref(m)
                except IndexError:
                    self.d = Ref(m)

            elif self.d == DatumType.POLY:
                self.t = self.d
                self.d = Polygon(m)
            elif self.d == DatumType.PALETTE:
                self.t = self.d
                self.d = Palette(m, check=False)
        elif self.t == DatumType.SINT16:
            self.d = struct.unpack("<H", m.read(2))[0]
        elif self.t == DatumType.UINT32:
            self.d = struct.unpack("<L", m.read(4))[0]
        elif self.t == DatumType.UINT64:
            self.d = struct.unpack("<Q", m.read(8))[0]
        elif self.t == DatumType.SINT64:
            self.d = struct.unpack("<Q", m.read(8))[0]
        elif self.t == DatumType.STRING:
            size = Datum(m)
            self.d = m.read(size.d).decode("utf-8")
        elif self.t == DatumType.BBOX:
            self.d = Bbox(m)
        elif self.t == DatumType.POINT or self.t == DatumType.POINT_2:
            self.d = Point(m)
        else:
            raise TypeError("(@ 0x{:0>12x}) Unknown datum type 0x{:0>4x}".format(m.tell(), self.t))

    def __repr__(self):
        data = ""
        base = "<Datum: +0x{:0>4x}; type: 0x{:0>4x}, ".format(
            self.s, self.t
        )
        
        try:
            if len(self.d) > 0x12 and not isinstance(self.d, str):
                data = "<length: 0x{:0>6x}>>".format(len(self.d))
            else:
                data = "data: {}>".format(self.d)
        except:
            data = "data: {}{:0>6x}{}>".format(
                "0x" if isinstance(self.d, int) else "", self.d,
                " ({:0>4d})".format(self.d) if isinstance(self.d, int) else ""
            )
            
        return base + data

class Array(Object):
    def __init__(self, m, size=None):
        self.start = m.tell()

        self.datums = []
        size = size if size else len(m.getbuffer())

        while m.tell() < size:
            self.datums.append(Datum(m, parent=self))

    def __repr__(self):
        return "<Array: 0x{:0>12x}; size: {:0>4d}>".format(self.start, len(self.datums))

class AssetHeader(Object):
    def __init__(self, m, check=True):
        if check:
            value_assert(Datum(m).d, HeaderType.ASSET, "asset header signature")

        self.data = Array(m)

    @property
    def type(self):
        return self.data.datums[1]

    @property
    def id(self):
        return self.data.datums[2]

    @property
    def name(self):
        if self.data.datums[4].t != DatumType.STRING:
            return None

        return self.data.datums[4]

    @property
    def ref(self):
        # TODO: Enumerate all types that have associated data chunks
        if self.type.d in (AssetType.SND, AssetType.FON):
            return self.data.datums[5]
        elif self.type.d in (AssetType.MOV, AssetType.IMG, AssetType.SPR):
            return self.data.datums[7]

        return None

    def __repr__(self):
        return "<AssetHeader: type: 0x{:0>4x}, id: 0x{:0>4x} ({:0>4d}){}{}>".format(
            self.type.d, self.id.d, self.id.d,
            " {}".format(self.ref.d) if self.ref else "",
            ", name: {}".format(self.name.d) if self.name else ""
        )

class AssetLink(Object):
    def __init__(self, m):
        # TODO: Determine the lengths of these asset links.
        self.type = Datum(m)
        self.data = Array(m)

    @property
    def ids(self):
        # For now, we just skip the even indices, as these are delimiters.
        return self.data.datums[::2]

class Ref(Object):
    def __init__(self, m, datums=1):
        chunk_assert(m, b'\x1b\x00')

        self.string = m.read(4).decode("utf-8")
        self.data = []
        for _ in range(datums):
            self.data.append(Datum(m))

    def id(self, string=False):
        return [self.string] if string else int(self.string[1:], 16)

    def __repr__(self):
        return "<Ref: {} ({:0>4d})>".format(self.string, self.id())

class MovieRef(Object):
    def __init__(self, m):
        self.refs = [Ref(m), Ref(m), Ref(m, datums=2)]
        value_assert(Datum(m).d, 0x001c)

    def id(self, string=False):
        return [r.id(string)[0] for r in self.refs]

    def __repr__(self):
        return("<MovieRef: ids: {}>".format(
            [r.string for r in self.refs])
        )

class Point(Object):
    def __init__(self, m):
        chunk_assert(m, b'\x10\x00')
        self.x = struct.unpack("<H", m.read(2))[0]

        chunk_assert(m, b'\x10\x00')
        self.y = struct.unpack("<H", m.read(2))[0]

    def __repr__(self):
        return "<Point: x: {}, y: {}>".format(self.x, self.y)

class Bbox(Object):
    def __init__(self, m):
        chunk_assert(m, b'\x0e\x00')
        self.point = Point(m)

        chunk_assert(m, b'\x0f\x00')
        self.dims = Point(m)

    def __repr__(self):
        return "<Bbox: {}, {}, {}, {}>".format(
            self.point.x, self.point.x + self.dims.x,
            self.point.y, self.point.y + self.dims.y
        )

class Polygon(Object):
    def __init__(self, m):
        size = Datum(m)

        self.points = []
        while m.read(2) == b'\x0e\x00':
            self.points.append(Point(m))

        m.seek(m.tell() - 2)
        value_assert(size.d, len(self.points), "polygon points", warn=True)

    def __repr__(self):
        return "<Polygon: points: {}>".format(len(self.points))

class Riff(Object):
    def __init__(self, m):
        chunk_assert(m, b'RIFF')
        size = struct.unpack("<L", m.read(4))[0]

        chunk_assert(m, b'IMTS')
        chunk_assert(m, b'rate')

        unk1 = Datum(m)
        m.read(2) # 00 00

        chunk_assert(m, b'LIST')
        self.size = struct.unpack("<L", m.read(4))[0]
        # assert size1 - size2 == 0x24, "Unexpected chunk size"

        self.start = m.tell()
        chunk_assert(m, b'data')

        self.m = m

    def next(self):
        if self.m.tell() - self.start < self.size:
            c = Chunk(self.m)
            return c
        else: return None

    def reset(self):
        self.m.seek(self.start + 0x04)


# External representations

class Palette(Object):
    def __init__(self, m, check=True):
        if check:
            value_assert(Datum(m).d, DatumType.PALETTE, "palette signature")
        self.colours = m.read(0x300)

class Root(Object):
    def __init__(self, m):
        value_assert(Datum(m).d, HeaderType.ROOT, "root signature")
        self.datums = Array(m)

    @property
    def id(self):
        return self.datums.datums[0]

    @property
    def name(self):
        try:
            if self.datums.datums[3].t == DatumType.STRING:
                return self.datums.datums[3]
        except:
            return None

class Image(Object):
    def __init__(self, m, dims=None, check=True):
        self.header = None
        self.dims = dims
        if not dims:
            value_assert(Datum(m).d, ChunkType.IMAGE, "image signature")
            self.header = Array(m, 0x16)

        if check:
            value_assert(m, b'\x00\x00', "image row header", warn=True)

        if self.compressed:
            self.raw = bytearray((self.width*self.height) * b'\x00')

            for h in range(self.height):
                self.offset = 0
                while True:
                    code = int.from_bytes(m.read(1), byteorder='little')

                    if code == 0x00: # control mode
                        op = int.from_bytes(m.read(1), byteorder='little')
                        if op == 0x00: # end of line
                            break

                        if op == 0x03: # offset for RLE
                            self.offset += struct.unpack("<H", m.read(2))[0]
                        else: # uncompressed data of given length
                            pix = m.read(op)

                            loc = (h * self.width) + self.offset
                            self.raw[loc:loc+len(pix)] = pix

                            if m.tell() % 2 == 1:
                                m.read(1)

                            self.offset += len(pix)
                    else: # RLE data
                        loc = (h * self.width) + self.offset

                        pix = m.read(1)
                        self.raw[loc:loc+code] = code * pix

                        self.offset += code

            self.raw = bytes(self.raw)
        else:
            self.raw = m.read(self.width*self.height)

        value_assert(len(self.raw), self.width*self.height, "image length ({} x {})".format(self.width, self.height), warn=True)

    def export(self, directory, filename, fmt="png", **kwargs):
        filename = os.path.join(directory, filename)

        if self.width == 0 and self.height == 0:
            logging.warning("Found image with length and width 0, skipping export")
            return

        if filename[-4:] != ".{}".format(fmt):
            filename += (".{}".format(fmt))

        image = PILImage.frombytes("P", (self.width, self.height), self.raw)
        if 'palette' in kwargs and kwargs['palette']:
            image.putpalette(kwargs['palette'].colours)

        image.save(filename, fmt)

    @property
    def compressed(self):
        return (self.header and self.header.datums[1].d) or self.dims

    @property
    def width(self):
        return self.dims.d.x if self.dims else self.header.datums[0].d.x

    @property
    def height(self):
        return self.dims.d.y if self.dims else self.header.datums[0].d.y

    def __repr__(self):
        return "<Image: size: {} x {}>".format(self.width, self.height)

class MovieFrame(Object):
    def __init__(self, m):
        m.seek(0)

        value_assert(Datum(m).d, ChunkType.MOV_2, "movie signature")
        self.header = Array(m, 0x26)
        self.image = Image(m, dims=self.header.datums[1])

class Movie(Object):
    # TODO: Do movies always come in their own RIFF?
    def __init__(self, riff, still=None):
        self.still = still
        self.chunks = []

        header = riff.next()
        while header:
            frames = []
            codes = {
                "header": int(header.code[1:], 16),
                "video": int(header.code[1:], 16) + 1,
                "audio": int(header.code[1:], 16) + 2
            }

            entry = riff.next()
            if not entry:
                break

            while entry and int(entry.code[1:], 16) == codes["video"]:
                frames.append(entry.data)
                entry = riff.next()

            if entry:
                if int(entry.code[1:], 16) == codes["audio"]:
                    self.chunks.append((Array(header.data), frames, entry))
                    header = riff.next()
                else: # We must have the next header entry
                    self.chunks.append((Array(header.data), frames, None))
                    header = entry

    def export(self, directory, filename, fmt=("png", "wav"), **kwargs):
        if self.still:
            self.still[0].image.export(directory, "still", fmt=fmt[0], **kwargs)
            with open(os.path.join(directory, "still.txt"), 'w') as still:
                for datum in Array(self.still[1]).datums:
                    print(repr(datum), file=still)

        frame_headers = open(os.path.join(directory, "frame_headers.txt"), 'w')
        image_headers = open(os.path.join(directory, "image_headers.txt"), 'w')

        for i, chunk in enumerate(self.chunks):
            for j, frame in enumerate(chunk[1]):
                logging.debug("Exporting animation cell ({}, {})".format(i, j))
                frame_type = Datum(frame).d

                if frame_type == ChunkType.MOV_2:
                    frame = MovieFrame(frame)

                    print(" --- {}-{} ---".format(i, j), file=image_headers)
                    for datum in frame.header.datums:
                        print(repr(datum), file=image_headers)

                    frame.image.export(directory, "{}-{}".format(i, j), fmt=fmt[0], **kwargs)
                elif frame_type == ChunkType.MOV_3:
                    array = Array(frame)

                    print(" --- {}-{} ---".format(i, j), file=frame_headers)
                    for datum in array.datums:
                        print(repr(datum), file=frame_headers)

            # TODO: Export sounds.

        frame_headers.close()
        image_headers.close()

    def __repr__(self):
        return "<Movie: chunks: {}>".format(len(self.chunks))

class Sprite(Object):
    def __init__(self):
        self.frames = []

    def append(self, m):
        header = Array(m, size=0x24)
        image = Image(m, dims=header.datums[1], check=False)

        self.frames.append((header, image))

    def export(self, directory, filename, fmt="png", **kwargs):
        frame_headers = open(os.path.join(directory, "frame_headers.txt"), 'w')

        for i, frame in enumerate(self.frames):
            print(" --- {}---".format(i), file=frame_headers)
            for datum in frame[0].datums:
                print(repr(datum), file=frame_headers)

            frame[1].export(directory, str(i), fmt=fmt, **kwargs)

        frame_headers.close()

class Font(Object):
    def __init__(self):
        self.glyphs = []

    def append(self, m):
        header = Array(m, size=0x22)
        glyph = Image(m, dims=header.datums[4])

        self.glyphs.append((header, glyph))

    def export(self, directory, filename, fmt="png", **kwargs):
        frame_headers = open(os.path.join(directory, "frame_headers.txt"), 'w')

        for i, glyph in enumerate(self.glyphs):
            print(" --- {}---".format(i), file=frame_headers)
            for datum in glyph[0].datums:
                print(repr(datum), file=frame_headers)

            glyph[1].export(directory, str(i), fmt=fmt, **kwargs)

        frame_headers.close()

class Sound(Object):
    def __init__(self, data):
        if isinstance(data, Riff):
            self.chunks = []
            entry = data.next()
            while entry:
                self.chunks.append(entry)
                entry = data.next()
        else:
            self.chunks = [data]

    def export(self, directory, filename, fmt="wav", **kwargs):
        filename = os.path.join(directory, filename)

        if filename[-4:] != ".{}".format(fmt):
            filename += (".{}".format(fmt))
            with subprocess.Popen(
                    ['ffmpeg', '-y', '-f', 's16le', '-ar', '11.025k', '-ac', '2', '-i', 'pipe:', filename],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE
            ) as process:
                for chunk in self.chunks:
                    process.stdin.write(chunk.data.read())

                process.communicate()

class CxtData(Object):
    def __init__(self, infile):
        with open(infile, mode='rb') as f:
            self.m = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
            logging.info("Opened context {}".format(infile))
            
            assert self.m.read(4) == b'II\x00\x00', "Incorrect file signature"
            struct.unpack("<L", self.m.read(4))[0]
            self.riff_count = struct.unpack("<L", self.m.read(4))[0]
            self.size = struct.unpack("<L", self.m.read(4))[0]

            self.palette = None
            self.root = None
            self.assets = {}

            self.make_assets()

    def make_assets(self):
        riff = Riff(self.m)

        # The first entry is palette or root entry
        logging.info("Finding header information...")
        entry = riff.next()
        value_assert(Datum(entry.data).d, ChunkType.HEADER, "header signature")

        try:
            logging.info("Searching for palette as first chunk...")
            self.palette = Datum(entry.data)
            assert self.palette.t == DatumType.PALETTE

            entry = riff.next()
        except AssertionError as e:
            self.palette = None
            entry.data.seek(0)
            logging.warning("Found no palette, assuming first chunk is root")

        value_assert(Datum(entry.data).d, ChunkType.HEADER, "header signature")
        self.root = Root(entry.data)

        # Now read all the asset headers
        logging.info("Reading asset headers...")
        asset_headers = {}
        movie_stills = {}

        entry = riff.next()
        while Datum(entry.data).d == ChunkType.HEADER:
            if Datum(entry.data).d != HeaderType.ASSET:
                break

            asset_header = AssetHeader(entry.data, check=False)

            if asset_header.ref and not isinstance(asset_header.ref.d, int):
                for ref in asset_header.ref.d.id(string=True):
                    asset_headers.update({ref: asset_header})
            else:
                self.assets.update({asset_header.id.d: (asset_header, None)})

                # TODO: Figure out palette handling more carefully.
                if asset_header.type.d == AssetType.PAL:
                    self.palette = asset_header.data.datums[-3]

            entry = riff.next()

        entry.data.seek(0)

        # Now read all the single-chunk assets
        logging.info("Reading single-chunk assets...")
        while entry:
            if entry.code == 'igod':
                value_assert(Datum(entry.data).d, ChunkType.HEADER, "header signature")

                # We do not use this data because we have a dictionary!
                AssetLink(entry.data)
            else:
                asset_header = asset_headers[entry.code]

                # TODO: Handle font chunks
                if asset_header.type.d == AssetType.IMG:
                    self.assets.update({asset_header.id.d: (asset_header, Image(entry.data))})
                elif asset_header.type.d == AssetType.SND:
                    self.assets.update({asset_header.id.d: (asset_header, Sound(entry))})
                elif asset_header.type.d == AssetType.SPR:
                    if asset_header.id.d not in self.assets:
                        self.assets.update({asset_header.id.d: [asset_header, Sprite()]})

                    self.assets[asset_header.id.d][1].append(entry.data)
                elif asset_header.type.d == AssetType.FON:
                    if asset_header.id.d not in self.assets:
                        self.assets.update({asset_header.id.d: [asset_header, Font()]})

                    self.assets[asset_header.id.d][1].append(entry.data)
                elif asset_header.type.d == AssetType.MOV: # A single still frame
                    if asset_header.id.d not in movie_stills:
                        movie_stills.update({asset_header.id.d: [MovieFrame(entry.data), None]})
                    else:
                        if Datum(entry.data).d == ChunkType.MOV_3:
                            movie_stills[asset_header.id.d][1] = entry.data
                        else:
                            logging.warning("Found movie with more than 1 still")
                else:
                    self.assets.update({asset_header.id.d: (asset_header, entry.data)})

            entry = riff.next()

        # Now read all multi-chunk assets in rest of file.
        # TODO: Determine where the junk data at the end comes from
        try:
            riff = Riff(self.m)
            logging.info("Reading multi-chunk assets...")
        except AssertionError as e:
            logging.warning(e)
            riff = None

        while riff:
            # Base the RIFF linking on the ID of the first chunk.
            entry = riff.next()

            for id, asset_header in asset_headers.items():
                if id == entry.code:
                    riff.reset()
                    if asset_header.type.d == AssetType.MOV:
                        self.assets.update({
                            asset_header.id.d: (asset_header, Movie(riff, still=movie_stills.get(asset_header.id.d)))
                        })
                    elif asset_header.type.d == AssetType.SND:
                        self.assets.update({asset_header.id.d: (asset_header, Sound(riff))})
                    else:
                        raise TypeError("Unhandled asset type requiring RIFFs: {}".format(asset_header.type.d))

                    break

            try:
                riff = Riff(self.m)
            except AssertionError:
                break

        self.unknown = self.m.read()
        logging.info("Parsing finished!")

    def export(self, directory):
        for id, asset in self.assets.items():
            logging.info("Exporting asset {}".format(id))

            path = os.path.join(directory, str(id))
            Path(path).mkdir(parents=True, exist_ok=True)

            with open(os.path.join(directory, str(id), "{}.txt".format(id)), 'w') as header:
                print(repr(asset[0]), file=header)
                for datum in asset[0].data.datums:
                    print(repr(datum), file=header)

            try:
                if asset[1]: asset[1].export(path, str(id), palette=self.palette.d if self.palette else None)
            except Exception as e:
                logging.warning("Could not export asset {}: {}".format(id, e))

    def __repr__(self):
        return "<Context: {:0>4d} (0x{:0>4x}){}>".format(
            self.root.id.d, self.root.id.d,
            ", name: {}".format(self.root.name.d) if self.root.name else ""
        )

def main(infile):
    global c
    c = CxtData(infile)
    c.export(os.path.split(infile)[1])

logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser(prog="cxt")
parser.add_argument("input")

args = parser.parse_args()
main(args.input)
