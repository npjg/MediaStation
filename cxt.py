#!/usr/bin/python3

import argparse
import logging

from enum import IntEnum
import struct
import io
import subprocess
import mmap

class IgodType(IntEnum):
    IMG  = 0x0007,
    MOV  = 0x0016,
    HSP  = 0x000b

class DatumType(IntEnum):
    NONE   =  0x0000,
    UINT8   = 0x0002,
    UINT16  = 0x0003,
    UINT32  = 0x0004,
    STRING  = 0x0012,
    PALETTE = 0x05aa,
    REF     = 0x001b,
    BBOX    = 0x000d,
    POINT   = 0x000f,
    POLY    = 0x001d,
    G_UNK1  = 0x001e,
    G_UNK2  = 0x001f,
    G_UNK3  = 0x05dc,
    A_UNK1  = 0x0011

class Object:
    def value_assert(self, m, target, type="value", warn=False):
        s = 0
        ax = m
        try:
            s = m.tell()
            ax = m.read(len(target))
        except AttributeError:
            pass

        msg = "(@ 0x{:0>12x}) Expected {} {}, received {}".format(s, type, target, ax)
        if warn and ax != target:
            logging.warning(msg)
        else:
            assert ax == target, msg

        return ax

    def chunk_assert(self, m, target, warn=False):
        self.value_assert(m, target, "chunk", warn)

    def align(self, m):
        if m.tell() % 2 == 1:
            m.read(1)

    def __format__(self, spec):
        return self.__repr__()

class Placeholder(Object):
    def __init__(self, m, l):
        self.data = m.read(l)

    def __repr__(self):
        return "\n  <Placeholder: size: {} data: {}>".format(
            len(self.data), " ".join("%02x" % b for b in self.data)
        )

class Ref(Object):
    def __init__(self, m, get_id=True):
        self.chunk_assert(m, b'\x1b\x00')

        self.a = m.read(4).decode("utf-8")
        self.i = Datum(m) if get_id else 0

    def __repr__(self):
        return("<Ref: a: {}, i: 0x{:0>4x} (0x{:0>4d})>".format(
            self.a, self.i.d, self.i.d)
        )

class MovieRef(Object):
    def __init__(self, m):
        self.refs = [Ref(m), Ref(m), Ref(m, get_id=False)]

    def __repr__(self):
        return("<MovieRef: ids: {}>".format([r.a for r in self.refs]))

class Polygon(Object):
    def __init__(self, m):
        size = Datum(m)

        self.points = []
        while m.read(2) == b'\x0e\x00':
            self.points.append(Point(m))

        m.seek(m.tell() - 2)
        self.value_assert(size.d, len(self.points), "polygon points")

    def __repr__(self):
        return "<Polygon: l: {}>".format(len(self.points))

class Bbox(Object):
    def __init__(self, m):
        self.chunk_assert(m, b'\x0e\x00')
        self.point = Point(m)

        self.chunk_assert(m, b'\x0f\x00')
        self.dims = Point(m)

    def __repr__(self):
        return "<Bbox: {}, {}, {}, {}>".format(
            self.point.x, self.point.x + self.dims.x,
            self.point.y, self.point.y + self.dims.y
        )

class Point(Object):
    def __init__(self, m):
        self.chunk_assert(m, b'\x10\x00')
        self.x = struct.unpack("<H", m.read(2))[0]

        self.chunk_assert(m, b'\x10\x00')
        self.y = struct.unpack("<H", m.read(2))[0]

    def __repr__(self):
        return "<Point: x: {}, y: {}>".format(self.x, self.y)

class Chunk(Object):
    def __init__(self, m):
        self.cc = m.read(4).decode("utf-8")
        self.size = struct.unpack("<L", m.read(4))[0]
        self.d = None

        self.s = m.tell()
        if self.cc == 'igod':
            self.d = Igod(m, self)
        else:
            self.d = Raw(m, self)
            logging.debug(self.d)

class Raw(Object):
    def __init__(self, m, parent):
        self.parent = parent
        self.header = []

        try:
            d = Datum(m)
            self.header.append(d)
            while m.tell() - self.parent.s < d.d:
                self.header.append(Datum(m))
                logging.debug(self.header[-1])
        except TypeError:
            m.seek(self.parent.s)

        self.s = m.tell()
        self.data = io.BytesIO(
            m.read(self.parent.size - (m.tell() - self.parent.s))
        )
        self.align(m)

    def __repr__(self):
        return "<Raw: 0x{:0>12x}; id: {}, size: 0x{:0>8x}>".format(
            self.s, self.parent.cc, len(self.data.getbuffer())
        )

class Datum(Object):
    def __init__(self, m, parent=None):
        self.parent = parent

        self.s = m.tell()
        self.d = None
        self.t = struct.unpack("<H", m.read(2))[0]

        if self.t == DatumType.UINT8:
            self.d = int.from_bytes(m.read(1), byteorder='little')
        elif self.t == DatumType.UINT16:
            self.d = struct.unpack("<H", m.read(2))[0]

            # TODO: Replace with parent types.
            if self.d == DatumType.PALETTE:
                self.t = self.d
                self.d = m.read(0x300)
            elif self.d == DatumType.REF:
                try:
                    d = None
                    if parent.t.d == IgodType.MOV:
                        d = MovieRef(m)
                    else:
                        d = Ref(m)

                    self.t = self.d
                    self.d = d
                except AssertionError:
                    m.seek(m.tell() - 2)
                    pass
            elif self.d == DatumType.POLY:
                self.t = self.d
                self.d = Polygon(m)
            elif self.d == DatumType.G_UNK1:
                self.t = self.d
                self.chunk_assert(m, b'\x10\x00')
                self.d = struct.unpack("<H", m.read(2))[0]
            elif self.d == DatumType.G_UNK2:
                self.t = self.d
                self.chunk_assert(m, b'\x02\x00')
                self.d = int.from_bytes(m.read(1), byteorder='little')
            elif self.d == DatumType.G_UNK3:
                self.t = self.d
                self.d = Placeholder(m, 0x0a)
        elif self.t == DatumType.UINT32:
            self.d = struct.unpack("<L", m.read(4))[0]
        elif self.t == DatumType.STRING:
            size = Datum(m)
            self.d = m.read(size.d).decode("utf-8")
        elif self.t == DatumType.BBOX:
            self.d = Bbox(m)
        elif self.t == DatumType.A_UNK1:
            self.d = Placeholder(m, 0x08)
        elif self.t == DatumType.POINT:
            self.d = Point(m)
        elif self.t == DatumType.NONE:
            self.d = 0
        else:
            raise TypeError("(@ 0x{:0>12x}) Unknown datum type: 0x{:0>4x}. Assuming UINT16".format(
                m.tell() - 2, self.t)
            )
            self.d = struct.unpack("<H", m.read(2))[0]

    def __repr__(self):
        data = ""
        base = "<Datum: 0x{:0>12x} (0x{:0>4x}); type: 0x{:0>4x}, ".format(
            self.s, self.s - self.parent.parent.s if self.parent else 0, self.t
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

class Igod(Object):
    def __init__(self, m, parent):
        self.parent = parent
        self.datums = []

        while m.tell() - self.parent.s < self.parent.size:
            self.datums.append(Datum(m, self))


        self.align(m)
        self.log()

    @property
    def t(self):
        try:
            return self.datums[3]
        except:
            return None

    @property
    def r(self):
        try:
            return self.datums[4]
        except:
            return None

    def log(self):
        for d, i in zip(self.datums, range(len(self.datums))):
            logging.debug("{:0>3d}: {}".format(i, d))

    def __repr__(self):
        return "<Igod: id: 0x{:0>4x} ({:0>4d}), t: 0x{:0>4x} (s: 0x{:0>12x}, S: 0x{:0>6x}, l: {:0>4d})>".format(
            self.r.d, self.r.d, self.t.d, self.parent.s, self.parent.size, len(self.datums)
        )

class Asset(Object):
    def __init__(self, i, c):
        assert i.r == r.cc, "Mismatched chunk identifiers: {} \ {}".format(i.r, r.cc)

        self.i = i
        self.r = r

class Riff(Object):
    def __init__(self, m):
        logging.debug("#### RIFF: {:0>12x} ####".format(m.tell()))
        self.chunk_assert(m, b'RIFF')
        size1 = struct.unpack("<L", m.read(4))[0]

        self.chunk_assert(m, b'IMTS')
        self.chunk_assert(m, b'rate')

        unk1 = Datum(m)
        m.read(2) # 00 00

        self.chunk_assert(m, b'LIST')
        size2 = struct.unpack("<L", m.read(4))[0]
        # assert size1 - size2 == 0x24, "Unexpected chunk size"

        start = m.tell()
        self.chunk_assert(m, b'data')

        self.chunks = []
        while m.tell() - start < size2:
            logging.debug("---- CHUNK: 0x{:0>12x} ----".format(m.tell()))
            self.chunks.append(Chunk(m))

class Cxt(Object):
    def __init__(self, infile):
        with open(infile, mode='rb') as f:
            self.m = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
            logging.debug("Opened context {}".format(infile))
            
            assert self.m.read(4) == b'II\x00\x00', "Incorrect file signature"
            struct.unpack("<L", self.m.read(4))[0]
            self.riff_count = struct.unpack("<L", self.m.read(4))[0]
            self.size = struct.unpack("<L", self.m.read(4))[0]

            self.riffs = []

    def parse(self):
        self.m.seek(0x10)

        while self.m.tell() < self.size:
            self.riffs.append(Riff(self.m))

    @property
    def assets(self):
        raise NotImplementedError

    def __repr__(self):
        root = self.riffs[0].chunks[0].d
        return "<Cxt: i: {}{}>".format(
            root.datums[2].d,
            ", n: {}".format(root.datums[5].d) if len(root.datums) > 5 else ""
        )

def main(infile):
    c = Cxt(infile)
    c.parse()

logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser(prog="cxt")
parser.add_argument("input")

args = parser.parse_args()
main(args.input)
