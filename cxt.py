#!/usr/bin/python3

import argparse
import logging

from enum import IntEnum
import struct
import subprocess
import mmap

class DatumType(IntEnum):
    UINT16  = 0x0003,
    UINT32  = 0x0004,
    STRING  = 0x0012,
    PALETTE = 0x05aa,
    ASTR    = 0x001b,
    BBOX    = 0x000d,
    POLY    = 0x001d,
    G_UNK1  = 0x001e

class Object:
    def chunk_assert(self, m, target):
        s = m.tell()
        ax = m.read(len(target))
        assert ax == target, "(@ 0x{:0>12x}) Expected chunk {}, received {}".format(s, target, ax)

    def __format__(self, spec):
        return self.__repr__()

class Placeholder(Object):
    def __init__(self, m, l):
        self.data = m.read(l)

    def __repr__(self):
        return "<Placeholder: l: {}>".format(len(self.data))

class Refs(Object):
    def __init__(self, m):
        self.refs = []

        while struct.unpack("<H", m.read(2))[0] == DatumType.ASTR:
            r = {"astring": m.read(4).decode("utf-8"), "id": Datum(m)}
            self.refs.append(r)

        m.seek(m.tell() - 2)

    def __repr__(self):
        return "{}<Refs: d: {}, l: {}>".format(
            "\n -- " if len(self.refs) > 1 else "",
            [r["astring"] for r in self.refs],
            ["0x{:0>4x}".format(r["id"].d) for r in self.refs] 
        )

class Polygon(Object):
    def __init__(self, m):
        size = Datum(m)

        self.points = []
        while m.read(2) == b'\x0e\x00':
            self.points.append(Point(m))

        m.seek(m.tell() - 2)

        assert len(self.points) == size.d, "Expected {} polygon points, got {}".format(
            size.d, len(self.points)
        )

    def __repr__(self):
        return "<Polygon: l: {}>".format(len(self.points))

class Bbox(Object):
    def __init__(self, m):
        self.chunk_assert(m, b'\x0e\x00')
        self.point = Point(m)

        self.chunk_assert(m, b'\x0f\x00')
        self.dims = Point(m)

    def __repr__(self):
        return "<bbox: {}, {}, {}, {}>".format(
            self.point.x, self.point.x + self.dims.x,
            self.point.y, self.point.y + self.dims.y
        )

class Point(Object):
    def __init__(self, m):
        self.chunk_assert(m, b'\x10\x00')
        self.x = struct.unpack("<H", m.read(2))[0]

        self.chunk_assert(m, b'\x10\x00')
        self.y = struct.unpack("<H", m.read(2))[0]

class Datum(Object):
    def __init__(self, m, parent=None):
        self.parent = parent

        self.s = m.tell()
        self.d = None
        self.t = struct.unpack("<H", m.read(2))[0]

        if self.t == DatumType.UINT16:
            self.d = struct.unpack("<H", m.read(2))[0]

            # TODO: Replace with parent types.
            if self.d == DatumType.PALETTE:
                self.t = self.d
                self.d = m.read(0x300)
            elif self.d == DatumType.ASTR:
                self.t = self.d
                self.d = Refs(m)
            elif self.d == DatumType.POLY:
                self.t = self.d
                self.d = Polygon(m)
            elif self.d == DatumType.G_UNK1:
                self.t = self.d
                self.d = Placeholder(m, 0x0b)
        elif self.t == DatumType.UINT32:
            self.d = struct.unpack("<L", m.read(4))[0]
        elif self.t == DatumType.STRING:
            size = Datum(m)
            self.d = m.read(size.d).decode("utf-8")
        elif self.t == DatumType.BBOX:
            self.d = Bbox(m)
        else:
            logging.warning("(@ 0x{:0>12x}) Unknown datum type: 0x{:0>4x}. Assuming UINT16".format(m.tell() - 2, self.t))
            self.d = struct.unpack("<H", m.read(2))[0]

    def __repr__(self):
        data = ""
        base = "<Datum: s: 0x{:0>12x} (0x{:0>4x}), t: 0x{:0>4x}, ".format(
            self.s, self.s - self.parent.s if self.parent else 0, self.t
        )

        try:
            if len(self.d) > 0x12 and not isinstance(self.d, str):
                data = "<l: 0x{:0>6x}>>".format(len(self.d))
            else:
                data = "d: {}>".format(self.d)
        except:
            data = "d: {}{:0>4x}>".format("0x" if isinstance(self.d, int) else "", self.d)

        return base + data

class Igod(Object):
    def __init__(self, m):
        self.chunk_assert(m, b'igod')
        self.size = struct.unpack("<L", m.read(4))[0]

        self.s = m.tell()
        self.datums = []
        while m.tell() - self.s < self.size:
            self.datums.append(Datum(m, self))

        if m.tell() % 2 == 1:
            m.read(1)

        for d in self.datums:
            logging.debug(d)

    def __repr__(self):
        return "<Igod: s: 0x{:0>12x}, S: 0x:{0>6x}, l: {:04>d}>".format(self.s, self.size, len(self.datums))

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

        self.igods = []
        while m.tell() - start < size2:
            logging.debug("---- IGOD: {:0>12x} ----".format(m.tell()))
            self.igods.append(Igod(m))

class Cxt(Object):
    def __init__(self, infile):
        with open(infile, mode='rb') as f:
            self.m = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
            logging.debug("Opened context %s" % (infile))
            
            assert self.m.read(2) == b'II', "Incorrect file signature"
            self.m.read(0x0e) # File size information?

    def parse(self):
        # TODO: Parse more RIFF chunks
        r = Riff(self.m)

def main(infile):
    c = Cxt(infile)
    c.parse()

logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser(prog="cxt")
parser.add_argument("input")

args = parser.parse_args()
main(args.input)
